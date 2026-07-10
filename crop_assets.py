import os

from PIL import Image


def standardise_image_dimensions(reference_image_path, source_image_path, output_image_path):
    """
    Center-crops a source image to match the exact aspect ratio of a reference image,
    then resizes it to the reference image's exact dimensions.
    """
    if not os.path.exists(reference_image_path):
        print(f"Error: Reference image '{reference_image_path}' not found.")
        return
    if not os.path.exists(source_image_path):
        print(f"Error: Source image '{source_image_path}' not found.")
        return

    # 1. Get dimensions and aspect ratio of the landscape target photo
    with Image.open(reference_image_path) as ref_img:
        target_w, target_h = ref_img.size
        target_ratio = target_w / target_h

    # 2. Open the portrait image to calculate cropping boxes
    with Image.open(source_image_path) as src_img:
        src_w, src_h = src_img.size
        src_ratio = src_w / src_h

        if src_ratio > target_ratio:
            # Source image is wider than target ratio -> Crop left and right sides
            new_width = int(target_ratio * src_h)
            horizontal_offset = (src_w - new_width) // 2
            crop_box = (horizontal_offset, 0, horizontal_offset + new_width, src_h)
        else:
            # Source image is taller than target ratio -> Center-crop top and bottom
            new_height = int(src_w / target_ratio)
            vertical_offset = (src_h - new_height) // 2
            crop_box = (0, vertical_offset, src_w, vertical_offset + new_height)

        # 3. Execute crop and downsample smoothly to target proportions
        cropped_img = src_img.crop(crop_box)
        final_resized_img = cropped_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # 4. Save over the existing file or create a matching copy
        final_resized_img.save(output_image_path, exact_type=src_img.format, quality=95)
        print(f"✔ Successfully processed '{source_image_path}' to match '{reference_image_path}' dimensions ({target_w}x{target_h}).")

if __name__ == "__main__":
    # Standardise the first image
    standardise_image_dimensions(
        reference_image_path="field_collection.jpg",
        source_image_path="bioassay_testing.jpg",
        output_image_path="bioassay_testing.jpg"
    )

    # Standardise the second image
    standardise_image_dimensions(
        reference_image_path="field_collection.jpg",
        source_image_path="field_surveillance.jpg",
        output_image_path="field_surveillance.jpg"
    )
