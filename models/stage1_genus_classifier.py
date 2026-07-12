"""
Stage 1 Genus Classifier: Transfer Learning with EfficientNet.

This module provides:
1. A fine-tuned EfficientNet-B0 model for genus classification (Anopheles/Culex/Aedes)
2. Data loading pipeline for folder-based image structure
3. Training, validation, and inference functions
4. Model checkpoint saving/loading

The model expects a standard directory structure:
    data/genus_training/
    ├── train/
    │   ├── Anopheles/
    │   ├── Culex/
    │   └── Aedes/
    ├── val/
    │   ├── Anopheles/
    │   ├── Culex/
    │   └── Aedes/
    └── test/
        ├── Anopheles/
        ├── Culex/
        └── Aedes/

Design choice: EfficientNet-B0 over ResNet-50
- EfficientNet: smaller, faster training, good accuracy, easier to deploy
- ResNet-50: slightly better accuracy but heavier, slower inference
- For field surveillance, speed and model size matter; EfficientNet is a good tradeoff

IMPORTANT: This is a training template. You must provide labeled data before
running training. Without real data, only inference on pre-trained checkpoints
is possible.
"""

from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms, models
from torchvision.datasets import ImageFolder
import os


# ========================================================================
# STAGE 1 MODEL CLASS
# ========================================================================


class Stage1GenusClassifier(nn.Module):
    """
    Fine-tuned EfficientNet-B0 for genus classification.
    
    Architecture:
    - Backbone: Pre-trained EfficientNet-B0 (ImageNet)
    - Head: Linear classifier (1280 -> 3 genus classes)
    """

    def __init__(self, num_classes: int = 3, pretrained: bool = True):
        super().__init__()
        self.num_classes = num_classes

        # Load pre-trained EfficientNet-B0
        self.backbone = models.efficientnet_b0(pretrained=pretrained)

        # Replace the final classification layer
        # EfficientNet-B0 has 1280 features in the final layer
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(1280, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)

    def freeze_backbone(self) -> None:
        """Freeze all backbone parameters; only train the classification head."""
        for param in self.backbone.features.parameters():
            param.requires_grad = False

    def unfreeze_backbone(self) -> None:
        """Unfreeze all backbone parameters for fine-tuning."""
        for param in self.backbone.parameters():
            param.requires_grad = True


# ========================================================================
# DATA LOADING & AUGMENTATION
# ========================================================================


def get_data_transforms() -> Dict[str, transforms.Compose]:
    """
    Return a dict of transform pipelines for train/val/test splits.
    
    Training: aggressive augmentation (rotation, brightness, etc.)
    Validation/Test: minimal augmentation (resize + normalize only)
    """
    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomVerticalFlip(p=0.5),
        transforms.RandomRotation(degrees=15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],  # ImageNet means
            std=[0.229, 0.224, 0.225],   # ImageNet stds
        ),
    ])

    val_test_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])

    return {
        "train": train_transform,
        "val": val_test_transform,
        "test": val_test_transform,
    }


def get_data_loaders(
    data_dir: str, batch_size: int = 32, num_workers: int = 4
) -> Tuple[DataLoader, DataLoader, Optional[DataLoader]]:
    """
    Load image data from a folder structure and return train/val/(optional test) DataLoaders.
    
    Expected structure:
        data_dir/
        ├── train/
        │   ├── Anopheles/
        │   ├── Culex/
        │   └── Aedes/
        ├── val/
        │   ├── Anopheles/
        │   ├── Culex/
        │   └── Aedes/
        └── test/ (optional)
            ├── Anopheles/
            ├── Culex/
            └── Aedes/
    """
    transforms_dict = get_data_transforms()

    train_dir = os.path.join(data_dir, "train")
    val_dir = os.path.join(data_dir, "val")
    test_dir = os.path.join(data_dir, "test")

    # Load datasets
    train_dataset = ImageFolder(train_dir, transform=transforms_dict["train"])
    val_dataset = ImageFolder(val_dir, transform=transforms_dict["val"])

    test_dataset = None
    if os.path.exists(test_dir):
        test_dataset = ImageFolder(test_dir, transform=transforms_dict["test"])

    # Create DataLoaders
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
    )
    test_loader = None
    if test_dataset:
        test_loader = DataLoader(
            test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
        )

    return train_loader, val_loader, test_loader


# ========================================================================
# TRAINING LOOP
# ========================================================================


def train_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    criterion: nn.Module,
    optimizer: optim.Optimizer,
    device: torch.device,
) -> float:
    """Run one training epoch. Return average loss."""
    model.train()
    total_loss = 0.0
    for images, labels in train_loader:
        images, labels = images.to(device), labels.to(device)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)

    return total_loss / len(train_loader.dataset)


def validate_epoch(
    model: nn.Module,
    val_loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> Tuple[float, float]:
    """Run one validation epoch. Return (average_loss, accuracy)."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in val_loader:
            images, labels = images.to(device), labels.to(device)

            outputs = model(images)
            loss = criterion(outputs, labels)

            total_loss += loss.item() * images.size(0)
            _, predicted = torch.max(outputs, 1)
            correct += (predicted == labels).sum().item()
            total += labels.size(0)

    avg_loss = total_loss / len(val_loader.dataset)
    accuracy = correct / total
    return avg_loss, accuracy


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    num_epochs: int = 20,
    learning_rate: float = 1e-3,
    device: Optional[torch.device] = None,
    checkpoint_path: str = "stage1_genus_classifier.pth",
) -> Dict[str, list]:
    """
    Train the Stage 1 genus classifier.
    
    Training strategy:
    1. First few epochs: backbone frozen, train only the head (quick convergence)
    2. Later epochs: unfreeze backbone, fine-tune entire network with lower LR
    
    Parameters
    ----------
    model : nn.Module
        The Stage1GenusClassifier instance
    train_loader : DataLoader
        Training data loader
    val_loader : DataLoader
        Validation data loader
    num_epochs : int
        Total epochs to train
    learning_rate : float
        Initial learning rate
    device : torch.device, optional
        Device to train on (default: cuda if available, else cpu)
    checkpoint_path : str
        Path to save the best model checkpoint
        
    Returns
    -------
    dict
        Dictionary with keys ["train_loss", "val_loss", "val_accuracy"] containing
        lists of values per epoch
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = model.to(device)
    criterion = nn.CrossEntropyLoss()

    # Training strategy: frozen backbone first, then fine-tune
    freeze_epochs = max(1, num_epochs // 3)  # Freeze for first third

    history = {"train_loss": [], "val_loss": [], "val_accuracy": []}
    best_val_acc = 0.0

    for epoch in range(num_epochs):
        # Unfreeze backbone after initial epochs
        if epoch == freeze_epochs:
            print(f"Epoch {epoch}: Unfreezing backbone for fine-tuning...")
            model.unfreeze_backbone()

        # Adjust learning rate
        current_lr = learning_rate if epoch < freeze_epochs else learning_rate * 0.1
        optimizer = optim.Adam(model.parameters(), lr=current_lr)

        # Train and validate
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = validate_epoch(model, val_loader, criterion, device)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_accuracy"].append(val_acc)

        print(
            f"Epoch {epoch + 1}/{num_epochs} | "
            f"Train Loss: {train_loss:.4f} | "
            f"Val Loss: {val_loss:.4f} | "
            f"Val Accuracy: {val_acc:.4f}"
        )

        # Save best checkpoint
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), checkpoint_path)
            print(f"  -> Saved checkpoint to {checkpoint_path}")

    return history


def load_checkpoint(model: nn.Module, checkpoint_path: str, device: torch.device) -> None:
    """Load model weights from a checkpoint."""
    state_dict = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(state_dict)
    print(f"Loaded checkpoint from {checkpoint_path}")


# ========================================================================
# INFERENCE
# ========================================================================


def predict_genus(
    model: nn.Module,
    image_tensor: torch.Tensor,
    device: torch.device,
    class_dict: Dict[int, str],
) -> Tuple[str, float]:
    """
    Predict the genus for a single image tensor.
    
    Parameters
    ----------
    model : nn.Module
        The trained Stage1GenusClassifier
    image_tensor : torch.Tensor
        A single image tensor (3, 224, 224) or batch
    device : torch.device
        Device to run inference on
    class_dict : dict
        Mapping from class index to class name
        
    Returns
    -------
    tuple
        (predicted_class_name, confidence_score)
    """
    model.eval()
    model = model.to(device)

    if image_tensor.ndim == 3:
        image_tensor = image_tensor.unsqueeze(0)

    image_tensor = image_tensor.to(device)

    with torch.no_grad():
        outputs = model(image_tensor)
        probabilities = torch.softmax(outputs, dim=1)
        confidence, predicted_idx = torch.max(probabilities, 1)

    predicted_class = class_dict[predicted_idx.item()]
    confidence_score = confidence.item()

    return predicted_class, confidence_score


if __name__ == "__main__":
    print("Stage 1 Genus Classifier Module Loaded")
    print("Expected image folder structure:")
    print("  data/genus_training/")
    print("  |-- train/")
    print("  |   |-- Anopheles/")
    print("  |   |-- Culex/")
    print("  |   `-- Aedes/")
    print("  |-- val/")
    print("  |   |-- Anopheles/")
    print("  |   |-- Culex/")
    print("  |   `-- Aedes/")
    print("  `-- test/ (optional)")
    print()
    print("To train, use: train_model(...) after loading data with get_data_loaders(...)")
