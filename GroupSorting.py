import os
import clip
import torch
from PIL import Image
from tqdm import tqdm
from sklearn.cluster import DBSCAN
import numpy as np
import shutil
from collections import Counter
from typing import List, Tuple
from multiprocessing import freeze_support
from torch.utils.data import Dataset, DataLoader

# ----- SETTINGS -----
INPUT_FOLDER = "D:/KFMB-DATABASE/Webp"
OUTPUT_FOLDER = "D:/KFMB-DATABASE/Grouped"
BATCH_SIZE = 64
SIMILARITY_EPS = 0.07  # Lower = stricter match
MIN_SAMPLES = 2
NUM_WORKERS = min(8, os.cpu_count() or 1)
# ---------------------


class ImageDataset(Dataset):
    def __init__(self, paths: List[str], preprocess) -> None:
        self.paths = paths
        self.preprocess = preprocess

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, str]:
        path = self.paths[idx]
        img = Image.open(path).convert("RGB")
        return self.preprocess(img), path


def main() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess = clip.load("ViT-B/32", device=device)
    torch.set_num_threads(NUM_WORKERS)
    torch.backends.cudnn.benchmark = True

    # Step 1: Gather image paths
    image_paths: List[str] = []
    print("Scanning image files...")
    for fname in os.listdir(INPUT_FOLDER):
        if fname.lower().endswith((".webp", ".jpg", ".jpeg", ".png")):
            image_paths.append(os.path.join(INPUT_FOLDER, fname))

    # Step 2: Preprocess and batch encode
    embeddings: List[np.ndarray] = []
    valid_paths: List[str] = []

    print("Encoding images with CLIP...")
    dataset = ImageDataset(image_paths, preprocess)
    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        pin_memory=True,
        shuffle=False,
    )

    for batch_images, batch_paths in tqdm(loader):
        image_input = batch_images.to(device, non_blocking=True)
        with torch.no_grad():
            batch_features = model.encode_image(image_input).cpu().numpy()

        batch_features = batch_features / np.linalg.norm(batch_features, axis=1, keepdims=True)

        embeddings.extend(batch_features)
        valid_paths.extend(batch_paths)

    # Step 3: Cluster with DBSCAN
    print("Clustering embeddings...")
    X = np.array(embeddings)
    clustering = DBSCAN(eps=SIMILARITY_EPS, min_samples=MIN_SAMPLES, metric='cosine').fit(X)

    # Report cluster distribution
    counts = Counter(clustering.labels_)
    print("Cluster counts (excluding noise):")
    for label, count in counts.items():
        if label != -1:
            print(f"Cluster {label}: {count} images")
    print(f"Noise (unclustered): {counts.get(-1, 0)} images")

    # Step 4: Sort and copy images sequentially
    print("Copying images to output folder...")
    labels = clustering.labels_
    unique_labels = sorted({l for l in labels if l != -1})

    total_clustered = sum(count for label, count in Counter(labels).items() if label != -1)
    digits = len(str(total_clustered))
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    image_counter = 1
    for label in unique_labels:
        indices = [i for i, lbl in enumerate(labels) if lbl == label]
        cluster_embeds = X[indices]
        center = cluster_embeds.mean(axis=0)
        center /= np.linalg.norm(center)
        sims = cluster_embeds @ center
        ordering = [idx for idx, _ in sorted(zip(indices, sims), key=lambda x: x[1], reverse=True)]

        for idx in ordering:
            fname = os.path.basename(valid_paths[idx])
            prefix = f"{image_counter:0{digits}d}_"
            dst = os.path.join(OUTPUT_FOLDER, prefix + fname)
            shutil.copy(valid_paths[idx], dst)
            image_counter += 1

    print("✅ Done. Grouped images saved to:", OUTPUT_FOLDER)


if __name__ == "__main__":
    freeze_support()
    main()
