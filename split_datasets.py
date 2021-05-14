"""
This script combines the FGADR and IDRiD datasets and splits them into train/test
subsets. CSV files containing file paths are saved to `data/train.csv` and
`data/test.csv`. Ensure that you have run the pre-processing scripts first.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torchvision.transforms as T
from PIL import Image
from sklearn.model_selection import train_test_split
from torch import nn
from torchvision import models

from src.options.split import get_args
from src.transforms.crop import CropShortEdge


def load_model(path: Path) -> nn.Module:
    """Loads the pre-trained ResNet model for predicting image grades."""
    model = models.resnet50()
    fc_n_features = model.fc.in_features
    model.fc = nn.Linear(fc_n_features, 5)
    model.load_state_dict(torch.load(path))
    model.eval()

    return model


def make_fgadr(
    original_dir: str, processed_dir: str, exclude_grader_1: bool = True
) -> pd.DataFrame:
    """
    :param original_dir: Path to the original FGADR directory. We use this to get the
    original images (since they not edited by the preprocessing script).
    :param processed_dir: Path to the preprocessed images, generated by the
    `preprocess_datasets.py` script.
    :param exclude_grader_1: Whether to exclude images graded by "grader 1" from the
    resulting paths. These images are coarsely annotated (inconsistent with other
    images), and can be excluded to avoid annotator bias.

    :returns: A pandas DataFrame containing paths to files in the FGADR dataset.
    """
    fgadr_original_path = Path(original_dir)
    fgadr_image_path = fgadr_original_path / "Original_Images"
    fgadr_label_path = Path(processed_dir) / "label"
    fgadr_inst_path = Path(processed_dir) / "inst"
    fgadr_csv_path = fgadr_original_path / "DR_Seg_Grading_Label.csv"

    fgadr_df = pd.read_csv(fgadr_csv_path, header=None, names=["File", "Grade"])

    if exclude_grader_1:
        grader = pd.to_numeric(fgadr_df["File"].str[5])
        not_grader_1_cond = grader != 1
        fgadr_df = fgadr_df.loc[not_grader_1_cond]

    fgadr_df = make_absolute_paths(
        fgadr_df, fgadr_image_path, fgadr_label_path, fgadr_inst_path
    )

    fgadr_df["Source"] = "FGADR"

    return fgadr_df


def make_idrid(processed_dir: str, predict_grades: bool = False) -> pd.DataFrame:
    """
    :param processed_dir: Path to the preprocessed images, generated by the
    `preprocess_datasets.py` script.
    :param predict_grades: Whether or not to use a model to predict the DR grades of
    these images.

    :returns: A pandas DataFrame containing paths to files in the IDRiD dataset.
    """
    idrid_root_path = Path(processed_dir)

    idrid_image_path = idrid_root_path / "img"
    idrid_label_path = idrid_root_path / "label"
    idrid_inst_path = idrid_root_path / "inst"

    idrid_files = [f.name for f in idrid_image_path.glob("**/*")]
    idrid_files.sort()

    idrid_df = pd.DataFrame(idrid_files, columns=["File"])

    idrid_df = make_absolute_paths(
        idrid_df, idrid_image_path, idrid_label_path, idrid_inst_path
    )

    # Predict labels.
    if predict_grades:
        model_path = Path("results/resnet/eyepacs/checkpoints/model_latest.pth")
        model = load_model(model_path)
        noisy_grades = predict_idrid(model, idrid_df)
    else:
        # Numpy's randint has an exclusive end point.
        noisy_grades = np.random.randint(0, 5, size=len(idrid_df))
    idrid_df["Grade"] = noisy_grades

    idrid_df["Source"] = "IDRiD"

    return idrid_df


def predict_idrid(model: nn.Module, idrid_df: pd.DataFrame) -> np.ndarray:
    """Predicts labels for the IDRiD dataset using the specified model."""
    img_size = 512
    transform = T.Compose([CropShortEdge(), T.Resize(img_size), T.ToTensor()])

    predictions = np.empty(len(idrid_df), dtype=int)
    for i, row in idrid_df.iterrows():
        image = Image.open(row["Image"])
        image = transform(image).unsqueeze(0)
        pred = model(image)
        pred = torch.argmax(pred)
        predictions[i] = pred.item()

    return predictions


def make_absolute_paths(
    df: pd.DataFrame, image_path: Path, label_path: Path, inst_path: Path
) -> pd.DataFrame:
    """Converts filenames to absolute paths using the specified root paths."""
    df["Image"] = str(image_path) + "/" + df["File"].astype(str)
    df["Label"] = str(label_path) + "/" + df["File"].astype(str)
    df["Instance"] = str(inst_path) + "/" + df["File"].astype(str)

    return df


def main():
    opt = get_args()

    data_path = Path("data")
    data_path.mkdir(parents=True, exist_ok=True)

    fgadr_df = make_fgadr(
        opt.fgadr_original_dir,
        opt.fgadr_processed_dir,
        exclude_grader_1=opt.exclude_grader_1,
    )

    idrid_df = make_idrid(opt.idrid_processed_dir, predict_grades=opt.predict_grades)

    diaretdb1_df = make_diaretdb1(
        opt.diaretdb1_processed_dir, predict_grades=opt.predict_grades
    )

    combined_df = pd.concat((fgadr_df, idrid_df, diaretdb1_df))

    # Remove redundant "File" column.
    combined_df = combined_df.drop("File", axis=1)

    combined_train, combined_test = train_test_split(
        combined_df, train_size=opt.train_size, random_state=opt.seed
    )

    print(f"FGADR : {len(fgadr_df)}")
    print(f"IDRiD: {len(idrid_df)}")
    print(f"DIARETDB1: {len(diaretdb1_df)}")

    print(f"Train: {len(combined_train)}")
    print(f"Test: {len(combined_test)}")

    combined_df.to_csv(data_path / "all.csv")
    combined_train.to_csv(data_path / "train.csv")
    combined_test.to_csv(data_path / "test.csv")


if __name__ == "__main__":
    main()
