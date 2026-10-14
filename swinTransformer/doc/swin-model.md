# Swin Transformer Model Overview

This page explains the model behind the website: what Swin Transformer is, how it is combined
with UperNet for semantic segmentation, and how each field in this repository's config files
maps to the architecture. If you only want to run the model, see
[Running inference](swin-inference.md). If you want to train it, see
[Training and fine-tuning](swin-training.md).

References:

* Paper: *Swin Transformer: Hierarchical Vision Transformer using Shifted Windows*
  (Liu et al., ICCV 2021), <https://arxiv.org/abs/2103.14030>
* Official segmentation code (the mmsegmentation fork this project relies on):
  <https://github.com/SwinTransformer/Swin-Transformer-Semantic-Segmentation>
* UperNet: *Unified Perceptual Parsing for Scene Understanding* (Xiao et al., ECCV 2018)

---

## 1. Why Swin Transformer?

The original Vision Transformer (ViT) splits an image into 16 × 16 patches and runs **global**
self-attention over all of them. That works for classification, but has two problems for dense
prediction tasks such as segmentation:

1. **Quadratic cost.** Global attention costs O((HW)²). A 512 × 512 input becomes expensive very
   quickly.
2. **A single scale.** ViT produces one low-resolution feature map, while segmentation heads
   (FPN, UperNet, …) expect a **feature pyramid** at strides 4, 8, 16, and 32, like a CNN gives.

Swin Transformer fixes both:

* **Window attention.** Self-attention runs only inside non-overlapping local windows of
  M × M tokens (M = 7 here). The cost becomes linear in image size.
* **Shifted windows.** Every other block shifts the window grid by ⌊M/2⌋ tokens, so information
  can flow between neighboring windows. Without the shift, each window would be isolated.
* **Hierarchical stages.** *Patch merging* layers halve the resolution and double the channels
  between stages. This produces a CNN-like pyramid that any existing segmentation head can use.

---

## 2. Architecture walkthrough (Swin-T, as used here)

For an input of size H × W × 3:

| Step            | Operation                                                    | Output size          | Config field              |
|-----------------|--------------------------------------------------------------|----------------------|---------------------------|
| Patch partition | 4 × 4 patches, linear embedding to C channels                | H/4 × W/4 × 96       | `patch_size=4`, `embed_dim=96` |
| Stage 1         | 2 Swin blocks                                                | H/4 × W/4 × 96       | `depths[0]=2`, `num_heads[0]=3` |
| Patch merging   | concatenate 2 × 2 neighbors, linear layer 4C → 2C            | H/8 × W/8 × 192      | —                         |
| Stage 2         | 2 Swin blocks                                                | H/8 × W/8 × 192      | `depths[1]=2`, `num_heads[1]=6` |
| Patch merging   |                                                              | H/16 × W/16 × 384    | —                         |
| Stage 3         | 6 Swin blocks                                                | H/16 × W/16 × 384    | `depths[2]=6`, `num_heads[2]=12` |
| Patch merging   |                                                              | H/32 × W/32 × 768    | —                         |
| Stage 4         | 2 Swin blocks                                                | H/32 × W/32 × 768    | `depths[3]=2`, `num_heads[3]=24` |

`out_indices=(0, 1, 2, 3)` makes the backbone return all four stage outputs. That is why the
decode head is configured with `in_channels=[96, 192, 384, 768]`.

### 2.1 A Swin block

Swin blocks come in pairs:

```
x ─▶ LayerNorm ─▶ W-MSA  (regular windows)  ─▶ + ─▶ LayerNorm ─▶ MLP ─▶ +
x ─▶ LayerNorm ─▶ SW-MSA (shifted windows)  ─▶ + ─▶ LayerNorm ─▶ MLP ─▶ +
```

* **W-MSA / SW-MSA**: multi-head self-attention inside 7 × 7 windows (`window_size=7`). The shifted
  variant moves the grid with a cyclic shift and uses an attention mask, so tokens that wrapped
  around from the opposite edge do not attend to each other.
* **Relative position bias**: each head learns a table of (2M − 1)² biases that are added to the
  attention logits based on the relative offset between two tokens. This is the
  `relative_position_bias_table` parameter, which the optimizer config excludes from weight decay.
* **Absolute position embedding**: optional and turned off (`ape=False`). Relative bias is
  enough, and leaving it off lets the model accept any input size.
* **MLP**: two linear layers with GELU and a hidden size of `mlp_ratio × C` (`mlp_ratio=4.`).
* **Stochastic depth**: `drop_path_rate=0.3` randomly skips residual branches during training.
  The rate grows linearly from 0 in the first block to 0.3 in the last block.
* **`qkv_bias=True`, `qk_scale=None`**: Q/K/V projections have a bias, and the attention scale is
  the default 1/√d.
* **`patch_norm=True`**: applies LayerNorm after patch embedding.
* **`use_checkpoint`**: gradient checkpointing. It saves GPU memory during **training** by
  recomputing activations in the backward pass, at the cost of roughly 20–30 % extra time. It has
  no effect on inference accuracy. The base config enables it, and the Swin-T config here turns it
  off.

---

## 3. The segmentation head: UperNet + auxiliary FCN

The model type is `EncoderDecoder`: backbone → decode head (→ auxiliary head, during training
only).

**UperNet (`UPerHead`)** fuses all four backbone stages:

1. A **Pyramid Pooling Module** on stage 4 pools at scales `pool_scales=(1, 2, 3, 6)` to capture
   global context.
2. An **FPN** top-down path merges the PPM output with stages 3, 2, and 1.
3. The fused features (`channels=512`) go through a 1 × 1 classifier with `num_classes` outputs,
   and the result is upsampled to the input size.

**Auxiliary head (`FCNHead`)** adds a lighter classifier on stage 3 (`in_index=2`,
`in_channels=384`). Its loss is weighted at `0.4` and adds extra supervision during training.
It is not used at inference time.

Both heads use pixel-wise `CrossEntropyLoss`. Pixels labeled `255` are ignored, which is how
padding and the "other" class in ADE20K are excluded.

`norm_cfg=dict(type='BN')` sets the normalization used inside the heads (the backbone uses
LayerNorm). See [Training and fine-tuning](swin-training.md#bn-vs-syncbn) for when to switch it to
`SyncBN`.

---

## 4. Model variants

Only the Swin-T config is included in this repository, but the larger variants only change a
few fields. The ADE20K numbers below are the official UperNet results at 512 × 512 with 160k
iterations.

| Variant | `embed_dim` | `depths`        | `num_heads`        | Head `in_channels`       | Aux `in_channels` | Params | mIoU (ss / ms) |
|---------|-------------|-----------------|--------------------|--------------------------|-------------------|--------|----------------|
| Swin-T  | 96          | `[2, 2, 6, 2]`  | `[3, 6, 12, 24]`   | `[96, 192, 384, 768]`    | 384               | ~60M   | 44.5 / 45.8    |
| Swin-S  | 96          | `[2, 2, 18, 2]` | `[3, 6, 12, 24]`   | `[96, 192, 384, 768]`    | 384               | ~81M   | 47.6 / 49.5    |
| Swin-B  | 128         | `[2, 2, 18, 2]` | `[4, 8, 16, 32]`   | `[128, 256, 512, 1024]`  | 512               | ~121M  | 48.1 / 49.7    |

To build, for example, a Swin-S config, copy
`configs/swin/upernet_swin_tiny_patch4_window7_512x512_160k_ade20k.py` and change `depths` (plus
`embed_dim`, `num_heads`, and the head `in_channels` for Swin-B). Use the matching
ImageNet-pretrained backbone for that variant.

**Choosing a variant for this website.** Inference runs once per upload while the user waits.
Swin-T is the best fit when the server has a single consumer GPU or must fall back to CPU.
Swin-S and Swin-B gain about 3–4 mIoU but need noticeably more GPU memory and time per image.

---

## 5. Input normalization and output format

* **Normalization**: images are converted to RGB and normalized with ImageNet statistics
  (`mean=[123.675, 116.28, 103.53]`, `std=[58.395, 57.12, 57.375]`). This must match how the
  backbone was pretrained, so keep these values when you train on your own data.
* **Test-time resize**: `img_scale=(2048, 512)` with `keep_ratio=True`. The image is scaled so it
  fits within 2048 × 512 while keeping its aspect ratio, which in practice makes the short side
  about 512 px.
* **Inference mode**: `test_cfg=dict(mode='whole')` runs the whole resized image in a single
  forward pass. Window attention handles arbitrary sizes because the backbone pads internally to
  multiples of the window size.
* **Output**: `inference_segmentor` returns a list with one `H × W` integer array per image, where
  each value is a class index from 0 to `num_classes - 1`. The demo script colors it with a palette
  (ADE20K by default) and blends it over the original image to produce the picture the user sees.
