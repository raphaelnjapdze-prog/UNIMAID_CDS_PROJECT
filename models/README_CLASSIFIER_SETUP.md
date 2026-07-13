# Mosquito Species Identification Classifier Setup

## Overview

This package implements a **two-stage deep learning pipeline** for African mosquito species identification:
- **Stage 1**: Genus classifier (Anopheles / Culex / Aedes)
- **Stage 2**: Genus-specific species/complex classifier (with cryptic complex constraints)

The pipeline uses **transfer learning** with EfficientNet-B0 backbone, fine-tuned on your labeled imagery data.

---

## Critical Biological Constraint: Cryptic Complexes

Several African Anopheles and Culex species are **morphologically indistinguishable** and cannot be separated by any image classifier, however well trained:

- **Anopheles gambiae complex**: gambiae s.s., coluzzii, arabiensis, merus, melas, quadriannulatus
  - *Resolution*: Requires **PCR** for species-level splitting
  - *Classifier output*: Always "An. gambiae complex" (single class)

- **Anopheles funestus group**: funestus s.s., rivulorum, parensis, leesoni, vaneedeni
  - *Resolution*: Requires **PCR** for species-level splitting
  - *Classifier output*: Always "An. funestus group" (single class)

**The pipeline enforces this constraint in code** — if you attempt to add individual complex members as separate output classes, training will fail with a clear assertion error.

Every prediction includes a **`resolution_level`** field:
- `"genus"`: Only genus predicted (Stage 2 failed or uncertain)
- `"complex"`: Cryptic species complex (e.g., "An. gambiae complex")
- `"species"`: Individual species (morphologically distinguishable, e.g., "An. nili")

Downstream code must respect this field; never assume higher precision than the resolution level supports.

---

## Minimum Viable Dataset Sizes

For a workable first model with acceptable generalization, use these **industry rule-of-thumb minimums**:

### Per-Class Images

| Scenario | Minimum per class |
|----------|-------------------|
| Good transfer learning (ImageNet pretrained) | **100–200 images** |
| Moderate transfer learning | **300–500 images** |
| Weak transfer learning | **500–1000 images** |
| From scratch (not recommended) | **2000+ images** |

### Overall Dataset Size

- **Stage 1 (Genus)**: ~300–600 total images (100–200 per genus)
- **Stage 2 (Anopheles)**: ~1,200–2,000 total images (100–200 per class; 12 classes)
- **Stage 2 (Culex)**: ~1,100–2,000 total images (100–200 per class; 11 classes)
- **Stage 2 (Aedes)**: ~2,000–4,000 total images (100–200 per class; 20 classes)

### Critical Caveats

1. **Transfer learning is essential**: Without ImageNet pretraining, you need 10x more data.
2. **Quality > Quantity**: 200 clear, well-framed specimen images beat 1000 blurry, poorly composed ones.
3. **Taxonomic balance**: Ensure each class has roughly equal representation. Severe imbalance (e.g., one class with 10 images, another with 500) degrades accuracy.
4. **Reproducibility**: For publication or regulatory use, document your dataset rigorously (collection dates, locations, collector IDs, slide reference numbers if applicable).

---

## Handling Class Imbalance

Real-world field surveys often have **extreme class imbalance**:
- Common species (e.g., *Culex quinquefasciatus*) may have thousands of specimens
- Rare species (e.g., *An. moucheti*) may have only tens

### Strategy 1: Weighted Loss (Recommended for Mild Imbalance)

The training scripts use **weighted Cross-Entropy Loss** by default. For a class with *n* samples out of *N* total:

```
class_weight = N / (num_classes * n)
```

Classes with fewer samples get higher loss weights, forcing the model to learn them better.

**Implementation**:
```python
# In training_script_stage2.py
class_counts = {class_idx: count for class_idx, count in enumerate(count_per_class)}
class_weights = torch.tensor(
    [len(dataset) / (len(class_counts) * class_counts[i]) 
     for i in range(len(class_counts))],
    dtype=torch.float,
    device=device
)
criterion = nn.CrossEntropyLoss(weight=class_weights)
```

### Strategy 2: Oversampling (For Severe Imbalance)

If one class has 500 images and another has 10, use random oversampling:

```python
from torch.utils.data import WeightedRandomSampler

# Calculate sample weights (inverse of class frequencies)
sample_weights = [1.0 / class_counts[target] for target in dataset.targets]
sampler = WeightedRandomSampler(
    weights=sample_weights, 
    num_samples=len(dataset), 
    replacement=True
)

# Create loader with sampler
train_loader = DataLoader(dataset, batch_size=32, sampler=sampler)
```

### Strategy 3: Undersampling (For Extreme Imbalance, Use Carefully)

Randomly drop majority-class samples to balance the dataset. **Trade-off**: Loses data, but training is faster.

```python
# Not recommended unless you have >5000 majority images and <50 minority images
```

### Recommended Approach

1. **First**, use **weighted loss** (default in training scripts)
2. If validation accuracy plateaus, add **light oversampling** (e.g., oversample minorities by 2–3x)
3. Monitor validation metrics per class using **per-class recall/precision** (not just overall accuracy)

Example monitor:
```python
def per_class_accuracy(predictions, labels, num_classes):
    for c in range(num_classes):
        mask = labels == c
        if mask.sum() > 0:
            acc_c = (predictions[mask] == labels[mask]).float().mean()
            print(f"Class {c}: {acc_c:.3f}")
```

---

## Directory Structure

### Stage 1 (Genus) Training Data

```
data/genus_training/
├── train/
│   ├── Anopheles/
│   │   ├── spec_001.jpg
│   │   ├── spec_002.jpg
│   │   └── ...
│   ├── Culex/
│   │   ├── spec_001.jpg
│   │   └── ...
│   └── Aedes/
│       └── ...
├── val/
│   ├── Anopheles/
│   ├── Culex/
│   └── Aedes/
└── test/
    ├── Anopheles/
    ├── Culex/
    └── Aedes/
```

### Stage 2 (Anopheles Species) Training Data

```
data/anopheles_species_training/
├── train/
│   ├── An. gambiae complex/
│   │   ├── specimen_001.jpg
│   │   └── ...
│   ├── An. funestus group/
│   │   ├── specimen_001.jpg
│   │   └── ...
│   ├── An. nili/
│   ├── An. moucheti/
│   ├── An. pharoensis/
│   ├── An. squamosus/
│   ├── An. coustani/
│   ├── An. rufipes/
│   ├── An. wellcomei/
│   ├── An. maculipalpis/
│   ├── An. demeilloni/
│   └── An. stephensi/
├── val/
│   ├── An. gambiae complex/
│   └── ...
└── test/
    ├── An. gambiae complex/
    └── ...
```

**Important**: Folder names MUST exactly match the class names in `ANOPHELES_CLASSES` (or `CULEX_CLASSES`, `AEDES_CLASSES`).

---

## Training Workflow

### Step 1: Train Stage 1 (Genus Classifier)

```python
from models.stage1_genus_classifier import (
    Stage1GenusClassifier,
    get_data_loaders,
    train_model,
)

# Load data
train_loader, val_loader, test_loader = get_data_loaders(
    data_dir="data/genus_training",
    batch_size=32,
)

# Create and train model
model = Stage1GenusClassifier(num_classes=3, pretrained=True)
history = train_model(
    model=model,
    train_loader=train_loader,
    val_loader=val_loader,
    num_epochs=20,
    learning_rate=1e-3,
    checkpoint_path="models/stage1_genus_classifier.pth",
)
```

### Step 2: Train Stage 2 (Specialist Classifiers)

```python
from models.stage2_specialist_classifiers import (
    create_anopheles_classifier,
    get_specialist_data_loaders,
    train_specialist_model,
)

# Load Anopheles training data
train_loader, val_loader, test_loader = get_specialist_data_loaders(
    data_dir="data/anopheles_species_training",
    batch_size=32,
)

# Create and train
model = create_anopheles_classifier(pretrained=True)
history = train_specialist_model(
    model=model,
    train_loader=train_loader,
    val_loader=val_loader,
    num_epochs=20,
    learning_rate=1e-3,
    checkpoint_path="models/stage2_anopheles.pth",
)

# Repeat for Culex and Aedes
```

### Step 3: Run Inference

```python
from models.inference_pipeline import MosquitoIdentificationPipeline

pipeline = MosquitoIdentificationPipeline(
    stage1_checkpoint="models/stage1_genus_classifier.pth",
    stage2_checkpoints={
        "Anopheles": "models/stage2_anopheles.pth",
        "Culex": "models/stage2_culex.pth",
        "Aedes": "models/stage2_aedes.pth",
    }
)

result = pipeline.identify("specimen.jpg")
print(f"Species: {result['species']}")
print(f"Resolution: {result['resolution_level']}")
print(f"Confidence: {result['stage2_confidence']:.3f}")
```

---

## Key Implementation Details

### Transfer Learning Strategy

Both Stage 1 and Stage 2 use the same fine-tuning approach:

1. **Epochs 1–7** (frozen backbone):
   - Only train the classification head (new 3–12 fully-connected layers)
   - Learns fast (quick convergence)
   - High learning rate (1e-3)

2. **Epochs 8–20** (unfrozen backbone):
   - Fine-tune the entire EfficientNet backbone
   - Lower learning rate (1e-4)
   - Slower convergence but learns deeper features specific to mosquito morphology

### Why EfficientNet-B0?

| Model | Params | Accuracy | Speed | Mobile-Ready |
|-------|--------|----------|-------|--------------|
| EfficientNet-B0 | 5.3M | 77.1% | ★★★★★ | ✓ |
| ResNet-50 | 25.5M | 76.1% | ★★★ | ✗ |
| MobileNetV2 | 3.5M | 71.9% | ★★★★★ | ✓ |
| ViT-B | 86M | 81.1% | ★★ | ✗ |

EfficientNet-B0 balances **accuracy**, **speed**, and **deployment feasibility** for field surveillance applications.

---

## Expected Performance

With ~150–200 images per class and proper class balance:

- **Stage 1 (Genus)**: 85–95% top-1 accuracy
- **Stage 2 (Species)**: 70–85% top-1 accuracy (varies by genus; Aedes is easier than Anopheles)

Performance will degrade significantly if:
- Dataset is <100 images per class
- Classes are severely imbalanced (10:1 or worse)
- Image quality is poor (blurry, overexposed, not centered)
- Cryptic complex constraint is violated (individual complex members as separate classes)

---

## Common Issues & Solutions

### Issue: Severe overfitting (train loss ↓, val loss ↑)

**Solutions**:
1. Reduce model capacity: Use EfficientNet-B0 instead of larger variants
2. Increase augmentation: Add more transforms (rotation, color jitter)
3. Add dropout: Already set to 0.2 in the classifier head; increase if needed
4. Collect more data: Best solution long-term

### Issue: One class accuracy is much worse than others

**Solutions**:
1. Check for class imbalance: Use weighted loss (default)
2. Inspect images: Are they blurry, poorly framed, or different quality than other classes?
3. Oversample the minority class: 2–3x oversampling via WeightedRandomSampler
4. Increase that class's weight manually in the loss function

### Issue: Stage 2 prediction falls back to Stage 1 (genus) too often

**Solutions**:
1. Check Stage 2 validation accuracy: Should be >50% for reasonable confidence
2. Increase `stage2_confidence_threshold` in `inference_pipeline.py` (currently 0.4)
3. Collect more training data for underrepresented classes
4. Verify no individual cryptic complex members are included as separate classes

---

## Next Steps

1. **Collect imagery**: Follow the directory structure above. Aim for 150–300 images per class.
2. **Run QC**: Use `utils/image_quality_control.py` to reject blurry/underexposed images before training.
3. **Train Stage 1**: See "Training Workflow" above.
4. **Train Stage 2**: Repeat for each genus.
5. **Test & Validate**: Evaluate on test split; compute per-class metrics.
6. **Deploy**: Use `inference_pipeline.py` in Streamlit apps or other applications.

---

## References

- **EfficientNet**: Tan, M. & Le, Q.V. (2019). EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks
- **Mosquito Taxonomy**: Coetzee et al. (2020); Gillies & Coetzee (1987); Jupp (1996)
- **Transfer Learning**: Yosinski et al. (2014). How transferable are features in deep neural networks?
