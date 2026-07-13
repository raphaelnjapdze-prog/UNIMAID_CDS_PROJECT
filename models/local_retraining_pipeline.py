"""Continuous local-model retraining pipeline for mosquito surveillance.

This module closes the loop between field photo screening and PCR confirmation.
It provides a simple, auditable workflow to:

1. Query confirmed specimen records from Supabase/Postgres
2. Export them into a standard image-folder layout for model training
3. Measure current-model accuracy on newly confirmed records before retraining
4. Retrain a Stage 2 specialist classifier on the expanded dataset
5. Compare the new model against the current model and only flag it for deployment
   when the validation improvement is meaningful
6. Log every retraining event with dataset size, accuracy, class breakdown, and timestamp

Design notes
------------
- This is intentionally simple and transparent. It is meant to be inspectable and
  easy to adjust, not to be a black-box training pipeline.
- The retraining cadence is intentionally batched. A single newly confirmed specimen
  is too noisy to meaningfully retrain on. The default batch threshold is 25 confirmed
  specimens, which is a practical minimum for a small local calibration dataset.
- For cryptic complexes, labels should be normalized to the parent complex/group class
  (for example, "An. gambiae complex") so the exported data remains compatible with
  the Stage 2 taxonomy.
"""

from __future__ import annotations

import io
import json
import os
import random
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

import torch
from PIL import Image

from models.mosquito_taxonomy import STAGE2_TAXONOMY
from models.stage2_specialist_classifiers import (
    Stage2SpecialistClassifier,
    create_anopheles_classifier,
    create_culex_classifier,
    create_aedes_classifier,
    get_specialist_data_loaders,
    train_specialist_model,
    load_specialist_checkpoint,
)


# ---------------------------------------------------------------------------
# CONFIGURATION / SAFETY THRESHOLDS
# ---------------------------------------------------------------------------

# IMPORTANT: retraining on every single new specimen is statistically weak and
# will overfit to noise. Batch retraining only after enough confirmed data has
# accumulated.
MIN_NEW_CONFIRMED_SAMPLES_PER_RETRAIN = 25
MIN_NEW_CONFIRMED_SAMPLES_PER_CLASS = 5
VALIDATION_IMPROVEMENT_MARGIN = 0.03  # 3 percentage points
DEFAULT_SPLIT_RATIO = 0.2
DEFAULT_BATCH_SIZE = 16
DEFAULT_NUM_EPOCHS = 6


class LocalRetrainingPipeline:
    """Continuous local-model retraining workflow for a genus-specific classifier."""

    def __init__(
        self,
        genus: str = "Anopheles",
        output_root: Optional[str] = None,
        current_checkpoint_path: Optional[str] = None,
        device: Optional[torch.device] = None,
    ):
        self.genus = genus
        self.output_root = Path(output_root or "data/continuous_learning")
        self.current_checkpoint_path = current_checkpoint_path
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.class_names = STAGE2_TAXONOMY[genus]["classes"]
        self.class_dict = STAGE2_TAXONOMY[genus]["class_dict"]
        self.model = self._build_model()

    def _build_model(self) -> Stage2SpecialistClassifier:
        if self.genus == "Anopheles":
            model = create_anopheles_classifier(pretrained=True)
        elif self.genus == "Culex":
            model = create_culex_classifier(pretrained=True)
        elif self.genus == "Aedes":
            model = create_aedes_classifier(pretrained=True)
        else:
            raise ValueError(f"Unsupported genus: {self.genus}")

        if self.current_checkpoint_path and os.path.exists(self.current_checkpoint_path):
            load_specialist_checkpoint(model, self.current_checkpoint_path, self.device)
        return model

    def _canonicalize_label(self, pcr_confirmed_species: Optional[str]) -> Optional[str]:
        """Map PCR-confirmed species to an export label compatible with Stage 2 taxonomy."""
        if not pcr_confirmed_species:
            return None

        label = str(pcr_confirmed_species).strip()
        for class_name in self.class_names:
            if class_name.lower() == label.lower():
                return class_name

        alias_map = {
            "an. gambiae s.s.": "An. gambiae complex",
            "an. coluzzii": "An. gambiae complex",
            "an. arabiensis": "An. gambiae complex",
            "an. merus": "An. gambiae complex",
            "an. melas": "An. gambiae complex",
            "an. quadriannulatus": "An. gambiae complex",
            "an. funestus s.s.": "An. funestus group",
            "an. rivulorum": "An. funestus group",
            "an. parensis": "An. funestus group",
            "an. leesoni": "An. funestus group",
            "an. vaneedeni": "An. funestus group",
        }
        return alias_map.get(label.lower())

    def _load_image_from_record(self, record: Dict[str, Any]) -> Optional[Image.Image]:
        """Load an image from a record's photo URL(s)."""
        photo_urls = record.get("photo_urls") or []
        if not photo_urls:
            return None

        for url in photo_urls:
            try:
                parsed = urlparse(str(url))
                if parsed.scheme in {"http", "https"}:
                    with urlopen(str(url)) as response:
                        data = response.read()
                else:
                    with open(str(url), "rb") as handle:
                        data = handle.read()

                image = Image.open(io.BytesIO(data)).convert("RGB")
                return image
            except Exception:
                continue
        return None

    def query_confirmed_records(self, client: Any) -> List[Dict[str, Any]]:
        """Query all confirmed specimen records from Supabase/Postgres."""
        if client is None:
            raise RuntimeError("Supabase client is not available")

        response = client.table("specimen_records").select("*").eq("pcr_status", "confirmed").execute()
        return response.data or []

    def export_confirmed_records_to_folders(
        self,
        records: List[Dict[str, Any]],
        output_root: Optional[str] = None,
        split_ratio: float = DEFAULT_SPLIT_RATIO,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Export confirmed records into train/val image folders by canonical label."""
        export_root = Path(output_root or self.output_root / "dataset_export")
        train_root = export_root / "train"
        val_root = export_root / "val"
        train_root.mkdir(parents=True, exist_ok=True)
        val_root.mkdir(parents=True, exist_ok=True)

        rng = random.Random(seed)
        exported = {"root": str(export_root), "train": [], "val": [], "class_counts": {}}

        for record in records:
            label = self._canonicalize_label(record.get("pcr_confirmed_species"))
            if not label:
                continue

            image = self._load_image_from_record(record)
            if image is None:
                continue

            class_dir = train_root / label
            class_dir.mkdir(parents=True, exist_ok=True)
            # Use a deterministic, collision-resistant filename.
            specimen_id = str(record.get("specimen_id") or "unknown")
            filename = f"{specimen_id}_{len(list(class_dir.glob('*'))):03d}.jpg"

            # Keep a simple deterministic split: each class is split independently.
            # If a class has only one image, keep it in training to avoid empty val partitions.
            class_records = [r for r in records if self._canonicalize_label(r.get("pcr_confirmed_species")) == label]
            class_index = class_records.index(record) if record in class_records else 0
            split_target = "val" if len(class_records) > 1 and rng.random() < split_ratio and class_index % 5 != 0 else "train"

            target_root = val_root if split_target == "val" else train_root
            target_dir = target_root / label
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / filename
            image.save(target_path)

            exported[split_target].append({"specimen_id": specimen_id, "label": label, "path": str(target_path)})
            exported["class_counts"][label] = exported["class_counts"].get(label, 0) + 1

        return exported

    def _prepare_image_tensor(self, image: Image.Image) -> torch.Tensor:
        """Convert PIL image to tensor using the same transforms as the specialist classifier."""
        from models.stage2_specialist_classifiers import get_specialist_data_transforms

        transform = get_specialist_data_transforms()["val"]
        return transform(image)

    def predict_record_label(self, record: Dict[str, Any], model: Optional[Stage2SpecialistClassifier] = None) -> Tuple[Optional[str], float]:
        """Predict the label for a single confirmed record."""
        image = self._load_image_from_record(record)
        if image is None:
            return None, 0.0

        model = model or self.model
        model.eval()
        image_tensor = self._prepare_image_tensor(image).unsqueeze(0).to(self.device)
        with torch.no_grad():
            outputs = model(image_tensor)
            probs = torch.softmax(outputs, dim=1)
            conf, idx = torch.max(probs, 1)

        predicted_idx = idx.item()
        predicted_label = self.class_dict.get(predicted_idx, str(predicted_idx))
        return predicted_label, float(conf.item())

    def evaluate_current_model_on_records(
        self,
        records: List[Dict[str, Any]],
        model: Optional[Stage2SpecialistClassifier] = None,
    ) -> Dict[str, Any]:
        """Measure accuracy of the current model on newly confirmed records before retraining."""
        model = model or self.model
        correct = 0
        total = 0
        per_class = {}
        predictions = []

        for record in records:
            target_label = self._canonicalize_label(record.get("pcr_confirmed_species"))
            if not target_label:
                continue

            predicted_label, _ = self.predict_record_label(record, model=model)
            if predicted_label is None:
                continue

            total += 1
            is_correct = predicted_label == target_label
            if is_correct:
                correct += 1

            per_class.setdefault(target_label, {"correct": 0, "total": 0})
            per_class[target_label]["total"] += 1
            if is_correct:
                per_class[target_label]["correct"] += 1

            predictions.append({
                "specimen_id": record.get("specimen_id"),
                "target": target_label,
                "predicted": predicted_label,
                "correct": is_correct,
            })

        accuracy = round(correct / total, 4) if total else None
        per_class_summary = {}
        for label, stats in per_class.items():
            per_class_summary[label] = {
                "total": stats["total"],
                "correct": stats["correct"],
                "accuracy": round(stats["correct"] / stats["total"], 4) if stats["total"] else None,
            }

        return {"total": total, "correct": correct, "accuracy": accuracy, "per_class": per_class_summary, "predictions": predictions}

    def retrain_and_compare(
        self,
        records: List[Dict[str, Any]],
        export_root: Optional[str] = None,
        log_path: Optional[str] = None,
        min_new_samples: int = MIN_NEW_CONFIRMED_SAMPLES_PER_RETRAIN,
        margin: float = VALIDATION_IMPROVEMENT_MARGIN,
        batch_size: int = DEFAULT_BATCH_SIZE,
        num_epochs: int = DEFAULT_NUM_EPOCHS,
    ) -> Dict[str, Any]:
        """Retrain on confirmed records and compare the new model to the current one."""
        if len(records) < min_new_samples:
            return {
                "status": "skipped",
                "reason": (
                    f"Not enough newly confirmed specimens for a meaningful retraining round. "
                    f"Need at least {min_new_samples}, received {len(records)}."
                ),
                "dataset_size": len(records),
            }

        export_root = Path(export_root or self.output_root / "retrain_runs" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
        export_root.mkdir(parents=True, exist_ok=True)
        exported = self.export_confirmed_records_to_folders(records, output_root=str(export_root))

        current_eval = self.evaluate_current_model_on_records(records, model=self.model)
        train_loader, val_loader, _ = get_specialist_data_loaders(str(export_root), batch_size=batch_size, num_workers=0)

        new_model = self._build_model()
        history = train_specialist_model(
            new_model,
            train_loader=train_loader,
            val_loader=val_loader,
            num_epochs=num_epochs,
            learning_rate=1e-3,
            device=self.device,
            checkpoint_path=str(export_root / "best_model.pth"),
        )

        new_val_accuracy = history["val_accuracy"][-1] if history.get("val_accuracy") else None
        current_val_accuracy = current_eval.get("accuracy")
        ready_to_deploy = False
        if isinstance(new_val_accuracy, (int, float)) and isinstance(current_val_accuracy, (int, float)):
            ready_to_deploy = (new_val_accuracy - current_val_accuracy) >= margin

        per_class_accuracy = self._evaluate_per_class_accuracy(new_model, val_loader)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dataset_size": len(records),
            "train_split_count": len(exported.get("train", [])),
            "val_split_count": len(exported.get("val", [])),
            "current_model_accuracy": current_val_accuracy,
            "new_model_validation_accuracy": new_val_accuracy,
            "improvement": round((new_val_accuracy - current_val_accuracy), 4) if isinstance(new_val_accuracy, (int, float)) and isinstance(current_val_accuracy, (int, float)) else None,
            "ready_to_deploy": ready_to_deploy,
            "per_class_accuracy": per_class_accuracy,
            "export_root": str(export_root),
        }

        if log_path:
            self._append_retraining_log(log_path, event)

        return event

    def _evaluate_per_class_accuracy(self, model: Stage2SpecialistClassifier, val_loader: Any) -> Dict[str, Any]:
        """Compute per-class validation accuracy for the retrained model."""
        model.eval()
        total_by_class: Dict[str, int] = {}
        correct_by_class: Dict[str, int] = {}

        with torch.no_grad():
            for images, labels in val_loader:
                images = images.to(self.device)
                outputs = model(images)
                _, preds = torch.max(outputs, 1)
                for pred, label in zip(preds.cpu().tolist(), labels.cpu().tolist()):
                    class_name = val_loader.dataset.classes[label]
                    total_by_class[class_name] = total_by_class.get(class_name, 0) + 1
                    if pred == label:
                        correct_by_class[class_name] = correct_by_class.get(class_name, 0) + 1

        return {
            cls: {
                "total": total_by_class[cls],
                "correct": correct_by_class.get(cls, 0),
                "accuracy": round(correct_by_class.get(cls, 0) / total_by_class[cls], 4) if total_by_class.get(cls, 0) else None,
            }
            for cls in sorted(total_by_class)
        }

    def _append_retraining_log(self, log_path: str, event: Dict[str, Any]) -> None:
        """Append a retraining event to a JSONL audit log."""
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_continuous_learning_workflow(
    client: Any,
    genus: str = "Anopheles",
    output_root: Optional[str] = None,
    current_checkpoint_path: Optional[str] = None,
    log_path: Optional[str] = None,
    device: Optional[torch.device] = None,
) -> Dict[str, Any]:
    """Full workflow: query confirmed records, export them, evaluate current model, retrain, and log results."""
    pipeline = LocalRetrainingPipeline(
        genus=genus,
        output_root=output_root,
        current_checkpoint_path=current_checkpoint_path,
        device=device,
    )

    records = pipeline.query_confirmed_records(client)
    if not records:
        return {"status": "no_confirmed_records", "records_found": 0}

    # For a local calibration pipeline, batch retraining is more statistically meaningful
    # than retraining on every single new specimen. The threshold below is intentional.
    if len(records) < MIN_NEW_CONFIRMED_SAMPLES_PER_RETRAIN:
        return {
            "status": "skipped",
            "reason": f"Need at least {MIN_NEW_CONFIRMED_SAMPLES_PER_RETRAIN} confirmed records before a meaningful retraining run.",
            "records_found": len(records),
        }

    export_result = pipeline.export_confirmed_records_to_folders(records, output_root=str(pipeline.output_root / "latest_dataset"))
    current_eval = pipeline.evaluate_current_model_on_records(records)
    retraining_result = pipeline.retrain_and_compare(
        records=records,
        export_root=str(pipeline.output_root / "retrain_runs"),
        log_path=log_path,
    )

    return {
        "status": retraining_result.get("status", "completed"),
        "records_found": len(records),
        "dataset_export": export_result,
        "current_model_accuracy": current_eval.get("accuracy"),
        "retraining": retraining_result,
    }
