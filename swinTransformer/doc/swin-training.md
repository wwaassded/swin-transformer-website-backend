# Training and Fine-tuning Swin Transformer

This guide covers how to train the segmentation model used by the website, either reproducing
the ADE20K model or fine-tuning it on your own classes, and how to put the resulting checkpoint
into the backend. It assumes the environment from [Running inference](swin-inference.md#1-environment)
is already installed.

All commands below are run from the root of the
[Swin-Transformer-Semantic-Segmentation](https://github.com/SwinTransformer/Swin-Transformer-Semantic-Segmentation)
clone. That repository provides `tools/train.py`, `tools/test.py`, and the distributed launch
scripts. This repository only contains the configs and the inference script.

---

## 1. The training config, field by field

The config used by the website is
[`configs/swin/upernet_swin_tiny_patch4_window7_512x512_160k_ade20k.py`](../utils/swinTransformer/configs/swin/upernet_swin_tiny_patch4_window7_512x512_160k_ade20k.py).
It inherits four base files and overrides parts of them:

```python
_base_ = [
    '../_base_/models/upernet_swin.py',        # architecture (backbone + heads)
    '../_base_/datasets/ade20k.py',            # data paths, augmentations, batch size
    '../_base_/default_runtime.py',            # logging, load_from / resume_from
    '../_base_/schedules/schedule_160k.py',    # optimizer, LR policy, iterations
]
```

mmcv merges these in order, and the child file wins. A nested dict in the child is **merged** with
the base, unless it contains `_delete_=True`, in which case it **replaces** the base entirely.

| Section      | Value in the Swin-T config                                                                  | Notes                                                                                     |
|--------------|---------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| Backbone     | `embed_dim=96, depths=[2,2,6,2], num_heads=[3,6,12,24], window_size=7, drop_path_rate=0.3` | See the [model overview](swin-model.md#2-architecture-walkthrough-swin-t-as-used-here)   |
| Heads        | `num_classes=150` in both `decode_head` and `auxiliary_head`                                | **Change both** when training on other classes                                           |
| Optimizer    | AdamW, `lr=6e-5`, `betas=(0.9, 0.999)`, `weight_decay=0.01`                                 | `_delete_=True` discards the base SGD settings                                            |
| No-decay     | `absolute_pos_embed`, `relative_position_bias_table`, `norm` → `decay_mult=0.`              | Standard for transformers: don't apply weight decay to position biases and norms         |
| LR schedule  | `poly`, `power=1.0`, linear warmup for 1500 iters from `lr × 1e-6`, `min_lr=0`, `by_epoch=False` | The LR decays linearly to 0 over the run                                               |
| Iterations   | 160,000 (`IterBasedRunner`)                                                                 | From `schedule_160k.py`                                                                   |
| Batch        | `samples_per_gpu=2`                                                                         | The reference recipe uses 8 GPUs × 2 = **16 images per iteration**                       |
| Evaluation   | mIoU every 16,000 iterations                                                                | From `schedule_160k.py`                                                                   |
| Work dir     | `../../tools/output`                                                                        | Relative to the directory you launch from. Override with `--work-dir`.                    |

### Data augmentation (from `ade20k.py`)

| Step                                     | Purpose                                                                   |
|------------------------------------------|---------------------------------------------------------------------------|
| `LoadAnnotations(reduce_zero_label=True)` | ADE20K label 0 ("other") becomes 255 (ignored), and 1–150 become 0–149  |
| `Resize(img_scale=(2048, 512), ratio_range=(0.5, 2.0))` | Random scale jitter from 0.5× to 2×                        |
| `RandomCrop(512×512, cat_max_ratio=0.75)` | Retries crops in which one class covers more than 75 % of the pixels    |
| `RandomFlip(prob=0.5)`                   | Horizontal flip                                                           |
| `PhotoMetricDistortion`                  | Random brightness, contrast, saturation, and hue                          |
| `Normalize` (ImageNet mean/std)          | Must match the backbone's pretraining                                     |
| `Pad(512×512, seg_pad_val=255)`          | Padded label pixels are ignored by the loss                               |

### Things to check in this repository's config copies

These configs differ from upstream in a few places that matter for training:

* <a id="checkpoint-interval"></a>**Checkpoint interval.** The Swin-T config sets
  `checkpoint_config = dict(interval=1)` with the comment "save a checkpoint every epoch", and
  `schedule_160k.py` sets `checkpoint_config = dict(by_epoch=True, interval=16000)`. After merging,
  the result is `dict(by_epoch=True, interval=1)`. Training uses `IterBasedRunner`, which counts
  **iterations**, not epochs, so epoch-based checkpointing does not map cleanly onto it. The
  upstream setting is:

  ```python
  checkpoint_config = dict(by_epoch=False, interval=16000)   # one checkpoint every 16k iterations
  ```

  Set this explicitly in your training config. Otherwise you may get a checkpoint on every
  iteration (filling the disk) or none until the end.

* **LR policy in the base schedule.** `schedule_160k.py` sets `by_epoch=True` for `lr_config`.
  The Swin-T config replaces it with `_delete_=True` and `by_epoch=False`, so it is correct there.
  If you write a new config that does *not* override `lr_config`, set `by_epoch=False` yourself.

* <a id="bn-vs-syncbn"></a>**BN vs SyncBN.** `upernet_swin.py` uses `norm_cfg = dict(type='BN')`
  in the heads, which works with the non-distributed `tools/train.py` on a single GPU. Upstream
  uses `SyncBN`. For multi-GPU distributed training, switch to SyncBN so the batch statistics are
  computed over the full global batch:

  ```python
  norm_cfg = dict(type='SyncBN', requires_grad=True)
  model = dict(decode_head=dict(norm_cfg=norm_cfg), auxiliary_head=dict(norm_cfg=norm_cfg))
  ```

  SyncBN fails if you launch without a distributed launcher.

* **`use_checkpoint`.** The base model enables gradient checkpointing, and the Swin-T config turns
  it off. If you run out of GPU memory, turn it back on with
  `--options model.backbone.use_checkpoint=True`.

---

## 2. Reproducing the ADE20K model

### 2.1 Prepare ADE20K

Download `ADEChallengeData2016.zip` (the SceneParsing benchmark, ~920 MB) from the MIT Scene
Parsing site (<http://sceneparsing.csail.mit.edu/>) and unpack it so the paths match `data_root`
in `ade20k.py`:

```
data/ade/ADEChallengeData2016/
├── images/
│   ├── training/        # 20,210 .jpg
│   └── validation/      #  2,000 .jpg
└── annotations/
    ├── training/        # 20,210 .png, pixel value = class id (0 = other)
    └── validation/      #  2,000 .png
```

`data_root` is relative to the directory you launch training from. Either create `data/` there
(a symlink works) or change `data_root` to an absolute path.

### 2.2 Get the ImageNet-pretrained backbone

Download `swin_tiny_patch4_window7_224.pth` (ImageNet-1K Swin-T classification weights) from the
[Swin Transformer classification repository](https://github.com/microsoft/Swin-Transformer). Training
from scratch without it is not practical: ADE20K is far too small to learn a transformer backbone
from random initialization.

### 2.3 Train

```bash
CONFIG=configs/swin/upernet_swin_tiny_patch4_window7_512x512_160k_ade20k.py
PRETRAIN=/path/to/swin_tiny_patch4_window7_224.pth

# Single GPU
python tools/train.py $CONFIG \
    --options model.pretrained=$PRETRAIN \
    --work-dir work_dirs/swin_t_ade20k

# 8 GPUs on one machine (the reference setup); switch the heads to SyncBN first (see §1)
tools/dist_train.sh $CONFIG 8 \
    --options model.pretrained=$PRETRAIN \
    --work-dir work_dirs/swin_t_ade20k
```

Useful flags for `tools/train.py` (this mmseg version uses `--options`, not `--cfg-options`):

| Flag                          | Effect                                                         |
|-------------------------------|----------------------------------------------------------------|
| `--work-dir DIR`              | Where logs, the dumped config, and checkpoints are written     |
| `--resume-from FILE`          | Continue an interrupted run (restores optimizer and iteration) |
| `--load-from FILE`            | Initialize weights from FILE, but start at iteration 0         |
| `--no-validate`               | Skip the periodic mIoU evaluation                              |
| `--seed N --deterministic`    | Reproducible runs                                              |
| `--options key=value …`       | Override any config field from the command line                |

### 2.4 Training on fewer GPUs

The recipe assumes 16 images per iteration. On one GPU with `samples_per_gpu=2`, each iteration
sees only 2 images, which means noisier gradients and fewer total images seen in 160k
iterations. Two options:

* **Raise the per-GPU batch** as far as memory allows: `--options data.samples_per_gpu=4`, and
  enable `model.backbone.use_checkpoint=True` to make room.
* **Scale the learning rate** roughly linearly with the total batch size. For example, with a
  total batch of 4 instead of 16, try `optimizer.lr=1.5e-5`. Then validate early: if mIoU at 16k
  iterations is far below the reference curve, adjust.

With a single BN-normalized GPU and a very small batch, the batch statistics in the heads become
unstable. Keeping at least 4 images per GPU helps.

### 2.5 Evaluate

```bash
CKPT=work_dirs/swin_t_ade20k/latest.pth

# Single-scale mIoU
python tools/test.py $CONFIG $CKPT --eval mIoU

# Multi-GPU
tools/dist_test.sh $CONFIG $CKPT 8 --eval mIoU

# Multi-scale + flip test (the "ms" number); --aug-test turns on scales 0.5–1.75 and flipping
tools/dist_test.sh $CONFIG $CKPT 8 --aug-test --eval mIoU

# Save colored predictions for visual inspection
python tools/test.py $CONFIG $CKPT --show-dir work_dirs/vis
```

A correctly trained Swin-T should land around **44.5 mIoU** single-scale on ADE20K val.

---

## 3. Fine-tuning on your own dataset

This is the usual reason to retrain: for example, segmenting only roads, buildings, and sky, or a
domain such as medical or satellite images.

### 3.1 Data layout

Use the same layout as ADE20K. Images and masks must share a base file name:

```
data/my_dataset/
├── images/      training/ xxx.jpg   validation/ yyy.jpg
└── annotations/ training/ xxx.png   validation/ yyy.png
```

Masks must be **single-channel PNGs whose pixel values are class indices** (0, 1, 2, …), not RGB
colors. Use `255` for pixels that should be ignored. If your labeling tool exports color masks,
convert them first:

```python
import numpy as np
from PIL import Image

COLOR_TO_ID = {(0, 0, 0): 0, (128, 64, 128): 1, (70, 70, 70): 2}

def convert(src, dst):
    rgb = np.array(Image.open(src).convert('RGB'))
    out = np.full(rgb.shape[:2], 255, dtype=np.uint8)   # unknown colors → ignore
    for color, idx in COLOR_TO_ID.items():
        out[(rgb == color).all(-1)] = idx
    Image.fromarray(out).save(dst)
```

### 3.2 Register a dataset class

Add `mmseg/datasets/my_dataset.py` to the Swin fork:

```python
from .builder import DATASETS
from .custom import CustomDataset


@DATASETS.register_module()
class MyDataset(CustomDataset):
    CLASSES = ('background', 'road', 'building')
    PALETTE = [[0, 0, 0], [128, 64, 128], [70, 70, 70]]

    def __init__(self, **kwargs):
        super(MyDataset, self).__init__(
            img_suffix='.jpg', seg_map_suffix='.png',
            reduce_zero_label=False,   # True only if 0 means "unlabeled" in your masks
            **kwargs)
```

Then import it in `mmseg/datasets/__init__.py` and add it to `__all__`.

`reduce_zero_label` is the most common source of off-by-one class bugs. Set it to `True` only when
0 means "unlabeled" in your masks, as it does in ADE20K. In that case `num_classes` is the number
of real classes, and label 0 is ignored. If 0 is a real class (such as "background"), keep it
`False`.

### 3.3 Write the config

Create `configs/swin/upernet_swin_tiny_patch4_window7_512x512_my_dataset.py`:

```python
_base_ = ['./upernet_swin_tiny_patch4_window7_512x512_160k_ade20k.py']

num_classes = 3
model = dict(
    decode_head=dict(num_classes=num_classes),
    auxiliary_head=dict(num_classes=num_classes))

dataset_type = 'MyDataset'
data_root = 'data/my_dataset'
data = dict(
    samples_per_gpu=4,
    train=dict(type=dataset_type, data_root=data_root,
               img_dir='images/training', ann_dir='annotations/training'),
    val=dict(type=dataset_type, data_root=data_root,
             img_dir='images/validation', ann_dir='annotations/validation'),
    test=dict(type=dataset_type, data_root=data_root,
              img_dir='images/validation', ann_dir='annotations/validation'))

# Start from the full ADE20K segmentation model rather than only the ImageNet backbone.
load_from = '/path/to/upernet_swin_tiny_patch4_window7_512x512.pth'

# Small datasets need far fewer than 160k iterations.
runner = dict(type='IterBasedRunner', max_iters=20000)
checkpoint_config = dict(by_epoch=False, interval=2000)
evaluation = dict(interval=2000, metric='mIoU')
lr_config = dict(warmup_iters=500)
```

Notes:

* **`load_from` vs `model.pretrained`.** `pretrained` loads only an ImageNet backbone.
  `load_from` loads the full ADE20K segmentation model (backbone + UperNet). The classifier layers
  (`conv_seg`) will not match a different `num_classes`. mmcv reports a size mismatch for them,
  skips them, and leaves them randomly initialized, which is what you want. Starting from ADE20K
  usually converges much faster than starting from ImageNet.
* **Iterations.** As a rule of thumb, aim for a few dozen passes over the training set:
  `max_iters ≈ epochs × num_train_images / total_batch_size`. Watch the validation mIoU to decide
  when to stop.
* **Input size.** If your images are much larger or more detailed than ADE20K (for example remote
  sensing), increase `crop_size` and the `img_scale` in both pipelines together.
* **Class imbalance.** If a small class is never predicted, add `class_weight=[...]` to the
  `loss_decode` of both heads.

### 3.4 Train and evaluate

```bash
python tools/train.py configs/swin/upernet_swin_tiny_patch4_window7_512x512_my_dataset.py \
    --work-dir work_dirs/swin_t_my_dataset
python tools/test.py configs/swin/upernet_swin_tiny_patch4_window7_512x512_my_dataset.py \
    work_dirs/swin_t_my_dataset/latest.pth --eval mIoU
```

Per-class IoU is printed in the table at the end. Use it to spot classes the model fails on.

---

## 4. Monitoring

* Logs are written to `<work-dir>/<timestamp>.log` and `.log.json` every 50 iterations
  (`log_config.interval`).
* To use TensorBoard, uncomment `dict(type='TensorboardLoggerHook')` in `default_runtime.py` and
  run `tensorboard --logdir <work-dir>`.
* The `.log.json` file has one JSON object per line, so it is easy to plot yourself:

  ```python
  import json
  import matplotlib.pyplot as plt

  rows = [json.loads(l) for l in open('work_dirs/swin_t_ade20k/xxx.log.json') if l.strip()]
  train = [r for r in rows if r.get('mode') == 'train']
  val = [r for r in rows if r.get('mode') == 'val']
  plt.plot([r['iter'] for r in train], [r['loss'] for r in train], label='loss')
  plt.twinx().plot([r['iter'] for r in val], [r['mIoU'] for r in val], 'r.-', label='mIoU')
  plt.show()
  ```

What healthy training looks like: `decode.loss_seg` drops quickly during warmup and then slowly
declines, `aux.loss_seg` follows it at a higher level, and validation mIoU rises at each
evaluation. If the loss becomes `nan`, lower the learning rate or check your masks for values
outside `[0, num_classes) ∪ {255}`.

---

## 5. Deploying the trained checkpoint to the website

1. Optionally shrink the checkpoint for serving. The optimizer state is only needed for resuming,
   so you can remove it:

   ```bash
   python tools/publish_model.py work_dirs/swin_t_my_dataset/latest.pth swin_t_my_dataset.pth
   ```

   The script appends a short hash to the output file name (`swin_t_my_dataset-<hash>.pth`).

2. Copy your config into this repository under
   `swinTransformer/utils/swinTransformer/configs/swin/`.
3. Point the backend at both files: set `swin_transformer_checkpoint` in
   [`tools/constant.py`](../tools/constant.py), and pass `--config` from
   [`tools/utils.py`](../tools/utils.py) (or change the default in `demo/swin_transformer.py`).
4. Make sure the colors match your classes. The demo defaults to the ADE20K palette. For a custom
   dataset, use `model.PALETTE` (see [inference §4](swin-inference.md#using-a-model-you-trained-yourself)).
5. Run the demo script by hand on a few validation images before uploading through the website.

---

## 6. Common training problems

| Problem                                                     | What to do                                                                                     |
|-------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| `CUDA out of memory`                                        | Lower `samples_per_gpu`, enable `model.backbone.use_checkpoint=True`, or use a smaller `crop_size` |
| mIoU stays near 0                                           | Check `num_classes` in **both** heads and `reduce_zero_label`, and confirm masks contain class ids, not RGB values |
| Errors about the default process group / distributed not being initialized | `SyncBN` with a non-distributed launch. Use `BN`, or start with `tools/dist_train.sh` |
| `KeyError: 'MyDataset is not in the dataset registry'`      | The dataset class is not imported in `mmseg/datasets/__init__.py`                              |
| Disk fills up with checkpoints                              | See [checkpoint interval](#checkpoint-interval) and set `by_epoch=False, interval=…`          |
| Training restarts from 0 after a crash                      | Use `--resume-from <work-dir>/latest.pth`, not `--load-from`                                   |
| Loss is `nan`                                               | Lower `optimizer.lr`, increase `warmup_iters`, check for invalid mask values                   |
