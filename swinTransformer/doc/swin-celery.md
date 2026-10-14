# Moving Swin Transformer Inference into Celery

**Status: planned.** This is the design for the README TODO "Hand the Swin Transformer
segmentation task to Celery". Nothing here is implemented yet.

---

## Why

Today `upload_file` calls `process_image`, which **blocks the Django request** while
`subprocess.run` starts a new Python process for the demo script. Every upload therefore pays for:

1. starting the interpreter and importing PyTorch, mmcv, and mmseg,
2. building the model from the config,
3. loading the checkpoint from disk and copying it to the GPU,
4. CUDA context setup and cuDNN autotuning (`cudnn_benchmark = True`),
5. and finally the forward pass itself, usually the smallest part.

Two concurrent uploads also mean two copies of the model in GPU memory at the same time, which
can easily run out of memory.

## Goals

* The upload request returns immediately with a task id.
* The model is **loaded once per worker process** and reused for every image.
* At most one inference runs on each GPU at a time.
* The frontend polls for the result (as noted in the `upload_file` docstring TODO).

---

## Design

### 1. A dedicated queue and worker for the GPU

Keep e-mail tasks and model tasks apart so a slow segmentation never delays a verification
e-mail:

```bash
# e-mail and other light tasks
celery -A swin worker -Q default -c 4
# model inference: one process per GPU, one task at a time
celery -A swin worker -Q segmentation -c 1 --pool=solo -n seg@%h
```

`--pool=solo` runs tasks in the worker's main process, so the model is loaded exactly once and
stays on the GPU. If you use the prefork pool (`-c 1`) instead, load the model in the **child**
process (the `worker_process_init` signal), never in the parent. CUDA cannot be re-initialized in
a forked process.

### 2. Load the model once per worker

```python
# swinTransformer/tasks.py
from celery import shared_task
from celery.signals import worker_ready

_model = None


def get_model():
    global _model
    if _model is None:
        from mmseg.apis import init_segmentor
        _model = init_segmentor(SWIN_CONFIG, swin_transformer_checkpoint, device=SWIN_DEVICE)
    return _model


@worker_ready.connect   # solo pool; with prefork, use worker_process_init instead
def warm_up(**_):
    get_model()          # load during worker startup instead of on the first request


@shared_task(bind=True, queue='segmentation', time_limit=120)
def segment_image(self, original_path, output_path):
    from mmseg.apis import inference_segmentor
    model = get_model()
    result = inference_segmentor(model, original_path)
    model.show_result(original_path, result, palette=model.PALETTE,
                      out_file=output_path, show=False)
    return output_path
```

`SWIN_CONFIG` and `SWIN_DEVICE` should become settings next to `swin_transformer_checkpoint`,
instead of the defaults currently hard-coded in `demo/swin_transformer.py`.

### 3. Request flow

```
POST upload/            → save original, segment_image.delay(...), return {task_id}
GET  segmentStatus/<id> → PENDING / STARTED / SUCCESS / FAILURE
                          on SUCCESS: create the DB records, update the cache, return the URLs
```

Creating the `OriginalImage` / `SegmentedImage` rows can happen either in the task (on success)
or in the status endpoint the first time it sees `SUCCESS`. Doing it in the task keeps the status
endpoint read-only. The task then also has to update the user's last cached history page in
Redis, as `upload_file` does today.

### 4. Settings that must change

| Setting                          | Current value | Problem                                                     | Suggested                                        |
|----------------------------------|---------------|-------------------------------------------------------------|--------------------------------------------------|
| `CELERY_TASK_TIME_LIMIT`         | `5` seconds   | Model loading alone takes longer, so tasks would be killed   | Override per task (`time_limit=120` above)       |
| `CELERY_WORKER_TASKS_PER_CHILD`  | `200`         | Each recycled child reloads the model                       | Fine to keep; it also protects against slow memory leaks |
| `CELERY_RESULT_BACKEND`          | `django-cache` | Results are lost if the cache entry is evicted             | Acceptable for polling; use `django-db` if results must persist |

### 5. Failure handling

* An out-of-memory or invalid image raises inside the task, and the task state becomes `FAILURE`.
  The status endpoint should map this to the existing `"something wrong in swin Transformer model"`
  message.
* After a CUDA out-of-memory error, call `torch.cuda.empty_cache()` before the next task.
* Do not auto-retry model failures the way `send_custom_email` does. A bad image will fail the
  same way every time.

---

## Frontend changes

* After upload, show a "segmenting…" state and poll the status endpoint every 1–2 seconds.
* Optionally, send an e-mail when a job finishes (respecting the [e-mail opt-out](prevent_email.md)).
