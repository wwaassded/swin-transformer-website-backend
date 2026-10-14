# Running Swin Transformer Inference

This guide covers everything needed to produce a segmentation map with the model: installing
the dependencies, getting a checkpoint, running the demo script by hand, and wiring it into the
backend. For background on the model itself, see the
[Swin Transformer model overview](swin-model.md).

---

## 1. Environment

The model code depends on the **official Swin Transformer fork of mmsegmentation**
(<https://github.com/SwinTransformer/Swin-Transformer-Semantic-Segmentation>). That fork is based
on mmsegmentation v0.11 and registers the `SwinTransformer` backbone used by the configs in this
repository.

> **Do not install a recent mmsegmentation from PyPI instead.** Newer releases (0.2x / 1.x) ship
> their own Swin backbone with different argument names (`embed_dims`, `pretrain_img_size`, …) and
> a different API, so the configs and the demo script here will not load.

### 1.1 Versions

| Package                    | Version used by this project                                       |
|----------------------------|--------------------------------------------------------------------|
| Python                     | 3.7 (the cached `.pyc` files are `cpython-37`)                     |
| PyTorch                    | `torch~=1.9.0+cu111` (from `requirements.txt`)                     |
| mmcv-full                  | A version accepted by the fork, checked at import time in `mmseg/__init__.py` |
| mmsegmentation (Swin fork) | Installed from source with `pip install -e .`                     |

mmcv-full has to be built for **your exact PyTorch and CUDA versions**. If no prebuilt wheel
exists for your combination, pip compiles it from source, which needs a CUDA toolkit and a C++
compiler. On Windows that means Visual Studio Build Tools.

### 1.2 Install

```bash
# PyTorch (adjust the CUDA tag to your driver; see pytorch.org "previous versions")
pip install torch==1.9.0+cu111 torchvision==0.10.0+cu111 \
    -f https://download.pytorch.org/whl/torch_stable.html

# mmcv-full built for that torch/CUDA pair
pip install mmcv-full -f https://download.openmmlab.com/mmcv/dist/cu111/torch1.9.0/index.html

# The Swin fork of mmsegmentation
git clone https://github.com/SwinTransformer/Swin-Transformer-Semantic-Segmentation.git
cd Swin-Transformer-Semantic-Segmentation
pip install -e .
pip install timm   # the Swin backbone imports helpers from timm
```

If `import mmseg` complains that your mmcv version is incompatible, install an mmcv-full version
inside the range listed in the fork's `mmseg/__init__.py`.

### 1.3 Sanity check

[`swinTransformer/utils/swinTransformer/fuck.py`](../utils/swinTransformer/fuck.py) prints the
PyTorch version, the CUDA version, and whether a GPU is visible:

```bash
python swinTransformer/utils/swinTransformer/fuck.py
# Torch version: 1.9.0+cu111
# CUDA version: 11.1
# CUDA available: True
# CUDA device: NVIDIA GeForce ...
```

Then confirm the fork is importable and the backbone is registered:

```bash
python -c "from mmseg.models import BACKBONES; print(BACKBONES.get('SwinTransformer'))"
```

If that prints `None`, the wrong mmsegmentation is on your path.

---

## 2. Getting a checkpoint

Two kinds of weights are involved. Make sure you use the right one:

| File                                          | What it is                                                      | Used for                   |
|-----------------------------------------------|-----------------------------------------------------------------|----------------------------|
| `swin_tiny_patch4_window7_224.pth`            | **Backbone only**, ImageNet-1K classification pretraining      | Starting point for training |
| `upernet_swin_tiny_patch4_window7_512x512.pth` | **Full segmentation model** (backbone + UperNet), ADE20K       | Inference on the website    |

* Download the ADE20K segmentation checkpoint from the model zoo table in the
  [Swin-Transformer-Semantic-Segmentation README](https://github.com/SwinTransformer/Swin-Transformer-Semantic-Segmentation#results-and-models),
  or train your own (see [Training and fine-tuning](swin-training.md)).
* `*.pth` files are listed in `.gitignore`. Keep checkpoints outside the repository and point the
  backend to them through configuration (§4).

Passing an ImageNet backbone-only file as `--checkpoint` will not raise an error, but the decode
head will stay randomly initialized and the output will be noise. If the result looks like
random colored blocks, check this first.

---

## 3. Running the demo script by hand

[`demo/swin_transformer.py`](../utils/swinTransformer/demo/swin_transformer.py) is the only entry
point the backend uses. It:

1. builds the model from a config and a checkpoint (`init_segmentor`),
2. runs one image through it (`inference_segmentor`),
3. colors the predicted class map with a palette and saves the blended image (`show_result_pyplot`).

### Arguments

| Argument       | Default                                                                       | Meaning                                         |
|----------------|-------------------------------------------------------------------------------|-------------------------------------------------|
| `--img`        | (required in practice)                                                        | Input image path                                 |
| `--outfile`    | (required in practice)                                                        | Where to write the colored result               |
| `--checkpoint` | (required in practice)                                                        | Segmentation checkpoint (`.pth`)                |
| `--config`     | `../configs/swin/upernet_swin_tiny_patch4_window7_512x512_160k_ade20k.py`     | Model config, **relative to the `demo/` folder** |
| `--device`     | `cuda:0`                                                                      | `cuda:N` or `cpu`                               |
| `--palette`    | `ade20k`                                                                      | Named color palette for the class map           |

### Example

```bash
cd swinTransformer/utils/swinTransformer/demo      # the default --config is relative to here
python swin_transformer.py \
    --img      ~/pictures/street.jpg \
    --outfile  ~/pictures/street_segmented.jpg \
    --checkpoint ~/models/upernet_swin_tiny_patch4_window7_512x512.pth
```

### CPU-only machines

```bash
python swin_transformer.py --device cpu --img … --outfile … --checkpoint …
```

This works, but expect a few seconds or more per image with Swin-T. Larger variants are much
slower.

### If `show_result_pyplot` raises a `TypeError`

The demo calls `show_result_pyplot(model, img, result, outfile, palette)`. Depending on the
mmsegmentation version you installed, the upstream function may not take an output path (it may
only display the figure). In that case, save the result with the segmentor's own method instead:

```python
model.show_result(args.img, result,
                  palette=get_palette(args.palette),
                  out_file=args.outfile,
                  show=False)
```

### Getting the raw class map instead of a picture

`result[0]` is an `H × W` NumPy array of class indices. This is useful if you want to report which
classes appear in an image, or how much of the image each one covers:

```python
import numpy as np
from mmseg.apis import init_segmentor, inference_segmentor

model = init_segmentor(config, checkpoint, device='cuda:0')
seg = inference_segmentor(model, 'street.jpg')[0]

ids, counts = np.unique(seg, return_counts=True)
for i, c in sorted(zip(ids, counts), key=lambda t: -t[1]):
    print(f'{model.CLASSES[i]:<20} {c / seg.size:6.2%}')
```

---

## 4. How the backend calls the model

[`swinTransformer/tools/utils.py`](../tools/utils.py) runs the demo script **as a separate
process for every upload**:

```python
subprocess.run(['python', settings.SWIN_TRANSFORMER,          # 'swin_transformer.py'
                '--checkpoint', swin_transformer_checkpoint,
                '--img', original_image,
                '--outfile', output_image],
               cwd=swin_transformer_working_dir)              # '.../demo'
```

* The output file name is `<name>_segmented_<timestamp>.<ext>`, saved next to the original in the
  Nginx image directory.
* Exit code `0` means success. Any other exit code makes `upload_file` return
  `"something wrong in swin Transformer model"`.
* `--config`, `--device`, and `--palette` are **not passed**, so the script defaults apply
  (Swin-T ADE20K config, `cuda:0`, ADE20K palette).

### Settings to adjust on a new machine

All of these are currently hard-coded for a Windows development machine:

| Where                                            | Name                           | Purpose                                         |
|--------------------------------------------------|--------------------------------|-------------------------------------------------|
| [`tools/constant.py`](../tools/constant.py)      | `swin_transformer_checkpoint`  | Absolute path to the segmentation `.pth`        |
| [`tools/constant.py`](../tools/constant.py)      | `swin_transformer_working_dir` | Folder containing the demo script               |
| [`tools/constant.py`](../tools/constant.py)      | `nginx_image_dir`              | Where originals and results are written         |
| [`tools/constant.py`](../tools/constant.py)      | `nginx_image_url_root`         | Public URL prefix for that folder               |
| [`swin/settings.py`](../../swin/settings.py)     | `SWIN_TRANSFORMER`             | Script file name inside the working directory   |

Also note that the subprocess runs `python` from `PATH`. If the model dependencies live in a
different virtual environment from Django, use that interpreter's full path (for example
`sys.executable`, or a dedicated setting).

### Using a model you trained yourself

If you change the dataset or the number of classes, the website must load the **matching config**
and **palette**, not only the new checkpoint:

1. Put your config under `configs/swin/` (or anywhere else), and either change the `--config`
   default in `swin_transformer.py` or add `'--config', <path>` to the `subprocess.run` call.
2. Point `swin_transformer_checkpoint` at the new `.pth`.
3. Named palettes (`ade20k`, `cityscapes`, `voc`) only exist for built-in datasets. For a custom
   dataset, pass `model.PALETTE` to the drawing call, or define your own color list.

---

## 5. Performance notes

* **Most of the per-request time goes to model loading, not to the forward pass.** Each upload
  starts a new Python interpreter, imports PyTorch and mmseg, builds the model, loads the
  checkpoint, and initializes CUDA. Keeping one process alive with the model already on the GPU
  removes all of that. See [Moving inference into Celery](swin-celery.md).
* **Image size.** The test pipeline resizes the image to fit within 2048 × 512 (short side about
  512). Very large uploads are downscaled first, so the cost is bounded, but decoding a huge JPEG
  still takes time and memory. Consider capping the upload size on the frontend.
* **Precision.** Running the model in FP16 (`model.half()` together with half-precision inputs)
  roughly halves memory on modern GPUs. Validate accuracy before relying on it, because this
  mmseg version was not designed around mixed-precision inference.
* **`cudnn_benchmark = True`** (in `default_runtime.py`) speeds up repeated inference at a fixed
  size, but adds a warm-up cost. With one process per request, every request pays that warm-up.

---

## 6. Troubleshooting

| Symptom                                                         | Likely cause / fix                                                                                       |
|-----------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| `KeyError: 'SwinTransformer is not in the backbone registry'`   | Wrong mmsegmentation installed. Install the Swin fork (§1).                                              |
| `AssertionError: MMCV==x.y.z is used but incompatible`          | mmcv-full is outside the range the fork accepts. Install a version within it.                           |
| `FileNotFoundError` for the config                              | The script was not started from `demo/`. Either `cd` there or pass an absolute `--config`.                |
| Output is random-looking colored blocks                         | A backbone-only (ImageNet) checkpoint, or a checkpoint whose `num_classes` does not match the config.    |
| `size mismatch for decode_head.conv_seg.weight` warning         | The checkpoint was trained with a different number of classes than the config. Use the matching config.  |
| `CUDA out of memory`                                            | Another process is holding the GPU, or the input is too large. Retry with `--device cpu` to confirm.     |
| `CUDA available: False` in the sanity check                     | The PyTorch build is CPU-only, or the CUDA tag does not match your driver. Reinstall PyTorch.            |
| Backend says `something wrong in swin Transformer model`        | Run the same command by hand (§3) with the paths from `constant.py` to see the real traceback.           |
