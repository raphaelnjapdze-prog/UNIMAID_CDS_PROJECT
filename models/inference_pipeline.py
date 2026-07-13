"""
Two-Stage Mosquito Species Identification Pipeline.

This module orchestrates Stage 1 (genus classification) → Stage 2 (species-level
classification) inference, handling model routing, uncertainty quantification, and
the critical "resolution_level" field that indicates whether the result is:
- "genus": Only genus-level prediction from Stage 1 (Stage 2 failed or skipped)
- "complex": Species/complex prediction that is a cryptic assembly (requires PCR for splitting)
- "species": Individual species prediction that is morphologically distinguishable

IMPORTANT: The "resolution_level" field MUST be provided to prevent downstream code
from misinterpreting predictions or assuming higher precision than supported by
morphological data alone.
"""

from typing import Dict, Optional, Tuple

import torch
from PIL import Image
import numpy as np

from models.stage1_genus_classifier import (
    Stage1GenusClassifier,
    get_data_transforms,
    load_checkpoint,
    predict_genus,
)
from models.stage2_specialist_classifiers import (
    Stage2SpecialistClassifier,
    create_stage2_classifiers,
    predict_species,
    load_specialist_checkpoint,
)
from models.mosquito_taxonomy import (
    STAGE1_CLASS_DICT,
    STAGE2_TAXONOMY,
    get_species_resolution_level,
)


class MosquitoIdentificationPipeline:
    """
    Two-stage mosquito species identification pipeline.
    
    Usage:
    ------
    # Initialize with pre-trained model checkpoints
    pipeline = MosquitoIdentificationPipeline(
        stage1_checkpoint="models/stage1_genus_classifier.pth",
        stage2_checkpoints={
            "Anopheles": "models/stage2_anopheles.pth",
            "Culex": "models/stage2_culex.pth",
            "Aedes": "models/stage2_aedes.pth",
        }
    )
    
    # Run inference on an image
    result = pipeline.identify(image_path="specimen.jpg")
    print(result["species"])  # e.g., "An. gambiae complex"
    print(result["resolution_level"])  # e.g., "complex"
    print(result["confidence"])  # confidence score for Stage 2 (or Stage 1 if Stage 2 skipped)
    """

    def __init__(
        self,
        stage1_checkpoint: str,
        stage2_checkpoints: Optional[Dict[str, str]] = None,
        device: Optional[torch.device] = None,
        stage1_confidence_threshold: float = 0.5,
        stage2_confidence_threshold: float = 0.4,
    ):
        """
        Initialize the two-stage pipeline with model checkpoints.
        
        Parameters
        ----------
        stage1_checkpoint : str
            Path to the Stage 1 genus classifier checkpoint
        stage2_checkpoints : dict or None
            Dictionary mapping genus names to Stage 2 specialist checkpoint paths.
            If None, only Stage 1 will be used (genus-level classification only).
        device : torch.device or None
            Device to run inference on (default: cuda if available, else cpu)
        stage1_confidence_threshold : float
            If Stage 1 confidence is below this, mark the prediction as uncertain
        stage2_confidence_threshold : float
            If Stage 2 confidence is below this, fall back to Stage 1 (genus only)
        """
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.stage1_confidence_threshold = stage1_confidence_threshold
        self.stage2_confidence_threshold = stage2_confidence_threshold

        # Load Stage 1 model
        self.stage1_model = Stage1GenusClassifier(num_classes=3, pretrained=False)
        load_checkpoint(self.stage1_model, stage1_checkpoint, self.device)

        # Load Stage 2 models (if provided)
        self.stage2_models = {}
        if stage2_checkpoints:
            for genus, checkpoint_path in stage2_checkpoints.items():
                # Determine number of classes for this genus
                num_classes = len(STAGE2_TAXONOMY[genus]["classes"])
                model = Stage2SpecialistClassifier(
                    num_classes=num_classes, genus=genus, pretrained=False
                )
                load_specialist_checkpoint(model, checkpoint_path, self.device)
                self.stage2_models[genus] = model

        # Data transforms
        self.transforms = get_data_transforms()

    def _prepare_image(self, image_input) -> torch.Tensor:
        """
        Convert various image input formats (PIL Image, numpy array, file path)
        to a normalized tensor ready for inference.
        """
        # Load from file if needed
        if isinstance(image_input, str):
            image = Image.open(image_input).convert("RGB")
        elif isinstance(image_input, np.ndarray):
            image = Image.fromarray(image_input).convert("RGB")
        else:
            image = image_input

        # Apply transforms
        image_tensor = self.transforms["val"](image)
        return image_tensor

    def identify(
        self,
        image_input,
        skip_stage2: bool = False,
    ) -> Dict[str, any]:
        """
        Run the full two-stage identification pipeline on an image.
        
        Parameters
        ----------
        image_input : str or PIL.Image or np.ndarray
            Input image (file path, PIL Image, or numpy array)
        skip_stage2 : bool
            If True, return only Stage 1 (genus) prediction without Stage 2
            
        Returns
        -------
        dict
            Result dictionary with keys:
            - genus : str
                Predicted genus (always present)
            - species : str
                Predicted species or complex (only if Stage 2 ran successfully)
            - resolution_level : str
                "genus" | "complex" | "species" indicating the precision level
            - stage1_confidence : float
                Confidence score from Stage 1
            - stage2_confidence : float or None
                Confidence score from Stage 2 (or None if skipped)
            - stage1_uncertain : bool
                True if Stage 1 confidence is below threshold
            - stage2_uncertain : bool or None
                True if Stage 2 confidence is below threshold (or None if skipped)
        """
        # Prepare image
        image_tensor = self._prepare_image(image_input)

        # Stage 1: Genus classification
        genus, stage1_conf = predict_genus(
            self.stage1_model, image_tensor, self.device, STAGE1_CLASS_DICT
        )
        stage1_uncertain = stage1_conf < self.stage1_confidence_threshold

        # Initialize result
        result = {
            "genus": genus,
            "species": genus,  # Default to genus if Stage 2 doesn't run
            "resolution_level": "genus",
            "stage1_confidence": float(stage1_conf),
            "stage2_confidence": None,
            "stage1_uncertain": stage1_uncertain,
            "stage2_uncertain": None,
        }

        # Stage 2: Species/complex classification (if models are loaded and not skipped)
        if skip_stage2 or genus not in self.stage2_models:
            return result

        specialist_model = self.stage2_models[genus]
        class_dict = STAGE2_TAXONOMY[genus]["class_dict"]

        species, stage2_conf, resolution_level = predict_species(
            specialist_model, image_tensor, self.device, class_dict
        )

        stage2_uncertain = stage2_conf < self.stage2_confidence_threshold

        # Update result with Stage 2 predictions
        result.update({
            "species": species,
            "resolution_level": resolution_level,
            "stage2_confidence": float(stage2_conf),
            "stage2_uncertain": stage2_uncertain,
        })

        # If Stage 2 is too uncertain, fall back to Stage 1 (genus only)
        if stage2_uncertain:
            result["species"] = genus
            result["resolution_level"] = "genus"

        return result

    def batch_identify(
        self,
        image_list,
        skip_stage2: bool = False,
    ) -> list:
        """
        Run identification on a batch of images.
        
        Parameters
        ----------
        image_list : list of str or PIL.Image or np.ndarray
            List of images (file paths, PIL Images, or numpy arrays)
        skip_stage2 : bool
            If True, return only Stage 1 predictions
            
        Returns
        -------
        list
            List of result dictionaries (one per image)
        """
        results = []
        for image in image_list:
            result = self.identify(image, skip_stage2=skip_stage2)
            results.append(result)
        return results


# ========================================================================
# CONVENIENCE FUNCTION FOR QUICK INFERENCE
# ========================================================================


def identify_mosquito(
    image_input,
    stage1_checkpoint: str = "models/stage1_genus_classifier.pth",
    stage2_checkpoints: Optional[Dict[str, str]] = None,
) -> Dict[str, any]:
    """
    Convenience function: instantiate pipeline and run inference in one call.
    
    Example:
    --------
    result = identify_mosquito("specimen.jpg", 
                               stage1_checkpoint="models/stage1.pth",
                               stage2_checkpoints={
                                   "Anopheles": "models/stage2_anopheles.pth",
                                   "Culex": "models/stage2_culex.pth",
                                   "Aedes": "models/stage2_aedes.pth",
                               })
    print(result["species"], "confidence:", result["stage2_confidence"])
    """
    pipeline = MosquitoIdentificationPipeline(
        stage1_checkpoint=stage1_checkpoint,
        stage2_checkpoints=stage2_checkpoints,
    )
    return pipeline.identify(image_input)


if __name__ == "__main__":
    print("Mosquito Identification Pipeline Module Loaded")
    print("\nUsage:")
    print("  pipeline = MosquitoIdentificationPipeline(...)")
    print("  result = pipeline.identify(image_path)")
    print("  print(result['species'], result['resolution_level'])")
