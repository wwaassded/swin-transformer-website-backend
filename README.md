# Swin Transformer Image Segmentation Website

A web application that performs **semantic segmentation** on user-uploaded images with a
**Swin Transformer** backbone and a **UperNet** decode head. Users upload a photo, the server
runs it through the model, and both the original and the color-coded segmentation map are kept
in the user's history so they can be browsed, searched, and deleted later.

This repository holds the **backend** and the **model integration**. The frontend lives at
<https://github.com/wwaassded/swin-transformer-website-frontend>.

| Layer         | Technology                                                                        |
|---------------|-----------------------------------------------------------------------------------|
| Model         | Swin-T backbone + UperNet head, built on mmsegmentation (Swin fork) + PyTorch     |
| Web framework | Django 3.2                                                                        |
| Storage       | MySQL (users, image records), Redis (history cache), Nginx (static image hosting) |
| Async tasks   | Celery (e-mail today; model inference is planned)                                 |

---

## The model at a glance

The segmentation model is the configuration
`upernet_swin_tiny_patch4_window7_512x512_160k_ade20k`:

| Item                | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| Backbone            | Swin-T (`embed_dim=96`, `depths=[2, 2, 6, 2]`, `window_size=7`)    |
| Decode head         | UperNet (`UPerHead`, 512 channels) + auxiliary FCN head            |
| Training data       | ADE20K (`ADEChallengeData2016`), 150 classes                       |
| Training crop       | 512 × 512                                                          |
| Schedule            | 160k iterations, AdamW, `lr=6e-5`, poly decay with linear warmup   |
| Reported accuracy\* | 44.5 mIoU (single scale) / 45.8 mIoU (multi-scale) on ADE20K val   |

\* Numbers come from the official Swin Transformer semantic segmentation release for this config.
A checkpoint you train yourself may differ.

The config files are in
[`swinTransformer/utils/swinTransformer/configs`](swinTransformer/utils/swinTransformer/configs),
and the inference entry point is
[`swinTransformer/utils/swinTransformer/demo/swin_transformer.py`](swinTransformer/utils/swinTransformer/demo/swin_transformer.py).

### Documentation

| Document                                                                   | What it covers                                                                        |
|----------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [Swin Transformer model overview](swinTransformer/doc/swin-model.md)       | How Swin and UperNet work, model variants, and how each config field maps to the architecture |
| [Running inference](swinTransformer/doc/swin-inference.md)                 | Environment setup, getting a checkpoint, running the demo script, and how the backend calls it |
| [Training and fine-tuning](swinTransformer/doc/swin-training.md)           | Preparing ADE20K or a custom dataset, training, evaluation, and deploying your own checkpoint |
| [Moving inference into Celery](swinTransformer/doc/swin-celery.md)         | Plan for asynchronous, load-once model inference                                       |
| [API manual](swinTransformer/doc/apiREADME.md)                             | Notes on the more involved backend APIs                                                |
| [History fuzzy search](swinTransformer/doc/fuzzy-search.md)                | Response format of the history search API                                              |
| [E-mail opt-out](swinTransformer/doc/prevent_email.md)                     | How users can avoid unwanted e-mail                                                    |

---

## Quick start: segment one image

The full walkthrough is in [Running inference](swinTransformer/doc/swin-inference.md). In short:

```bash
# 1. Install PyTorch, a matching mmcv-full, and the Swin fork of mmsegmentation
git clone https://github.com/SwinTransformer/Swin-Transformer-Semantic-Segmentation.git
cd Swin-Transformer-Semantic-Segmentation
pip install -e .

# 2. Check that PyTorch can see your GPU
python swinTransformer/utils/swinTransformer/fuck.py   # run from this repo's root

# 3. Run the demo script from its own directory (the default config path is relative to it)
cd swinTransformer/utils/swinTransformer/demo
python swin_transformer.py \
    --img /path/to/input.jpg \
    --outfile /path/to/output.jpg \
    --checkpoint /path/to/upernet_swin_tiny_patch4_window7_512x512.pth \
    --device cuda:0
```

To train or fine-tune the model, for example on your own classes, see
[Training and fine-tuning](swinTransformer/doc/swin-training.md).

---

## How a request becomes a segmentation map

```
Browser ──upload──▶ Django upload_file
                       │ 1. save the original under the Nginx image directory
                       │ 2. process_image() → subprocess:
                       │       python swin_transformer.py --checkpoint … --img … --outfile …
                       │       (cwd = swinTransformer/utils/swinTransformer/demo)
                       │ 3. on exit code 0, store both image URLs in MySQL
                       │ 4. update the user's cached history page in Redis
                       ▼
                 JSON with image id + URLs ──▶ the frontend shows both images via Nginx
```

Paths for the checkpoint, the working directory, and the Nginx image folder are set in
[`swinTransformer/tools/constant.py`](swinTransformer/tools/constant.py). The script name is
`SWIN_TRANSFORMER` in [`swin/settings.py`](swin/settings.py).

---

## Current TODO

* [X] ~~Delete images from the history page and keep the database and cache consistent while doing so~~
* [X] ~~Limit how many history images are cached per user and pick a suitable eviction policy~~
* [ ] We update the database first and then delete the cache entry. If the database write succeeds
      but the cache delete fails, the two can still get out of sync. How should this be handled?
* [ ] [Hand the Swin Transformer segmentation task to Celery](swinTransformer/doc/swin-celery.md)
* [X] ~~[Fuzzy search for images on the history page](swinTransformer/doc/fuzzy-search.md)~~
* [X] ~~E-mail activation at registration. This may change the user table, so store each user's
      e-mail address for later communication.~~
* [ ] [Should users be able to opt out of e-mail?](swinTransformer/doc/prevent_email.md)
* [ ] A user account should not be logged in on several devices at the same time
* [ ] Design a new page that shows the user's basic information and a few simple settings:
  1. Whether to receive e-mail
  2. Editing basic information
  3. Whether to support user avatars
* [ ] Model-side improvements (see the model docs):
  * [ ] Load the model once in a long-lived worker instead of starting a new process per request
  * [ ] Make the config, palette, and device configurable from settings instead of hard-coded defaults
  * [ ] Return the per-class pixel ratio alongside the colored map so the frontend can show a legend
* [ ] 🐶 Shouldn't there be a frontend TODO too?

## License

[MIT](LICENSE)
