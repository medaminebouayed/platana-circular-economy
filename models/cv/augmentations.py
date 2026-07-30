import random
import numpy as np
from PIL import Image, ImageDraw
import torch
import torchvision.transforms as T

# -----------------------------------------------------------------------------
# Helper: simple background-object mask based on background color heuristic
# -----------------------------------------------------------------------------
def get_object_mask(img: Image.Image) -> np.ndarray:
    """
    Computes a binary mask of the object in the image by examining the corners
    to detect if the background is light or dark.
    """
    img_np = np.array(img)
    if len(img_np.shape) == 3:
        gray = np.mean(img_np, axis=2)
    else:
        gray = img_np
    
    h, w = gray.shape
    # Corner pixels to detect background intensity
    corners = [gray[0, 0], gray[0, w-1], gray[h-1, 0], gray[h-1, w-1]]
    bg_val = np.mean(corners)
    
    if bg_val > 127:
        # Light background (e.g., bottle, cable)
        mask = gray < 235
    else:
        # Dark background
        mask = gray > 20
        
    return mask

# -----------------------------------------------------------------------------
# Helper: realistic color sampler for defects (avoid neon colors)
# -----------------------------------------------------------------------------
def get_realistic_color(base_color: np.ndarray) -> tuple[int, int, int]:
    """
    Samples a realistic defect color (rust, dirt, gray, darkened or brightened object color)
    to avoid giving the model easy neon color shortcuts.
    """
    choice = random.choice(["darken", "brighten", "rust", "gray"])
    if choice == "darken":
        # Dark stain / shadow / hole
        factor = random.uniform(0.1, 0.4)
        return tuple(np.clip(base_color * factor, 0, 255).astype(int))
    elif choice == "brighten":
        # Scratches, reflection, paint peel
        offset = random.uniform(50, 130)
        return tuple(np.clip(base_color + offset, 0, 255).astype(int))
    elif choice == "rust":
        # Typical rust color (reddish-brown)
        return (random.randint(100, 170), random.randint(45, 95), random.randint(20, 45))
    else:
        # Gray / dark dirt
        g = random.randint(15, 75)
        return (g, g, g)

# -----------------------------------------------------------------------------
# Anomaly 1: CutPaste (simulating broken, cut or damaged areas)
# -----------------------------------------------------------------------------
def apply_cutpaste(img: Image.Image, mask: np.ndarray) -> Image.Image:
    """
    Extracts a random patch from the object, applies rotation and color jitter,
    and pastes it onto another location of the object with soft feathered edges.
    """
    w, h = img.size
    
    # Get mask coordinates
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return img
    
    # Choose patch size
    pw = random.randint(15, 45)
    ph = random.randint(15, 45)
    
    # Choose random source within object
    idx_src = random.randint(0, len(ys) - 1)
    y_src, x_src = ys[idx_src], xs[idx_src]
    
    # Clip coordinates to stay within image bounds
    y_src = max(0, min(y_src, h - ph))
    x_src = max(0, min(x_src, w - pw))
    
    # Crop patch
    patch = img.crop((x_src, y_src, x_src + pw, y_src + ph))
    
    # Augment patch
    # 1. Color Jitter
    color_jitter = T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2)
    patch = color_jitter(patch)
    # 2. Rotation
    rot = random.randint(-45, 45)
    patch = patch.rotate(rot, expand=True, resample=Image.BICUBIC)
    
    # Get the new patch size after rotation
    pw_new, ph_new = patch.size
    
    # Create soft mask for pasting (feathering) to avoid sharp rectangular edges
    patch_mask = Image.new("L", (pw_new, ph_new), 0)
    draw_mask = ImageDraw.Draw(patch_mask)
    margin = max(2, min(pw_new // 8, ph_new // 8))
    draw_mask.rectangle([margin, margin, pw_new - margin - 1, ph_new - margin - 1], fill=255)
    patch_mask = T.functional.gaussian_blur(patch_mask, [5, 5], [1.5, 1.5])
    
    # Choose random destination within object
    idx_dst = random.randint(0, len(ys) - 1)
    y_dst, x_dst = ys[idx_dst], xs[idx_dst]
    
    y_dst = max(0, min(y_dst, h - ph_new))
    x_dst = max(0, min(x_dst, w - pw_new))
    
    # Paste
    img_copy = img.copy()
    img_copy.paste(patch, (x_dst, y_dst), patch_mask)
    return img_copy

# -----------------------------------------------------------------------------
# Anomaly 2: Scratches / Cracks
# -----------------------------------------------------------------------------
def apply_scratch(img: Image.Image, mask: np.ndarray) -> Image.Image:
    """
    Draws a random line on the object area with a realistic scratch color
    and feathered edges to prevent sharp graphic artifacts.
    """
    w, h = img.size
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return img
    
    # Choose line points
    idx1 = random.randint(0, len(ys) - 1)
    y1, x1 = ys[idx1], xs[idx1]
    
    # Length of scratch: 20 to 80 pixels
    length = random.randint(20, 80)
    angle = random.uniform(0, 2 * np.pi)
    
    x2 = int(x1 + length * np.cos(angle))
    y2 = int(y1 + length * np.sin(angle))
    
    # Keep end point inside image
    x2 = max(0, min(x2, w - 1))
    y2 = max(0, min(y2, h - 1))
    
    # Scratch color: sample image color and get realistic defect color
    img_np = np.array(img)
    base_color = img_np[y1, x1]
    color = get_realistic_color(base_color)
    
    # Draw scratch on a separate layer for soft blending
    scratch_layer = Image.new("RGB", (w, h), color)
    scratch_mask = Image.new("L", (w, h), 0)
    draw_mask = ImageDraw.Draw(scratch_mask)
    
    width = random.randint(1, 3)
    draw_mask.line([(x1, y1), (x2, y2)], fill=255, width=width)
    
    # Blur the mask to feather scratch edges
    scratch_mask = T.functional.gaussian_blur(scratch_mask, [3, 3], [0.8, 0.8])
    
    # Paste
    img_copy = img.copy()
    img_copy.paste(scratch_layer, (0, 0), scratch_mask)
    return img_copy

# -----------------------------------------------------------------------------
# Anomaly 3: Contamination / Spots
# -----------------------------------------------------------------------------
def apply_contamination(img: Image.Image, mask: np.ndarray) -> Image.Image:
    """
    Draws a random small spot on the object with a realistic stain color and
    smooth feathered boundaries.
    """
    w, h = img.size
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return img
    
    # Choose center
    idx = random.randint(0, len(ys) - 1)
    y, x = ys[idx], xs[idx]
    
    r = random.randint(3, 10)
    
    # Sample base color and get realistic defect color
    img_np = np.array(img)
    base_color = img_np[y, x]
    color = get_realistic_color(base_color)
    
    # Draw spot on a separate layer for soft blending
    spot_layer = Image.new("RGB", (2*r + 4, 2*r + 4), color)
    spot_mask = Image.new("L", (2*r + 4, 2*r + 4), 0)
    draw_mask = ImageDraw.Draw(spot_mask)
    draw_mask.ellipse([2, 2, 2*r + 1, 2*r + 1], fill=255)
    
    # Blur the mask to feather spot boundaries
    spot_mask = T.functional.gaussian_blur(spot_mask, [3, 3], [0.8, 0.8])
    
    # Paste
    img_copy = img.copy()
    img_copy.paste(spot_layer, (x - r - 2, y - r - 2), spot_mask)
    return img_copy

# -----------------------------------------------------------------------------
# Main Wrapper Function
# -----------------------------------------------------------------------------
def generate_synthetic_anomaly(img: Image.Image) -> tuple[Image.Image, str]:
    """
    Generates a random mask-aware synthetic anomaly on the given PIL Image.
    Returns: (augmented_img, defect_type)
    """
    mask = get_object_mask(img)
    anomaly_choice = random.choice(["scratch", "contamination", "broken"])
    
    if anomaly_choice == "scratch":
        return apply_scratch(img, mask), "scratch"
    elif anomaly_choice == "contamination":
        return apply_contamination(img, mask), "contamination"
    else:
        return apply_cutpaste(img, mask), "broken_small"

def get_train_transform(category: str):
    """
    Returns the default mask-aware training transform.
    """
    return T.Compose([
        T.Resize((256, 256)),
        T.RandomCrop(224),
        T.RandomHorizontalFlip(),
        T.RandomRotation(15),
        T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
