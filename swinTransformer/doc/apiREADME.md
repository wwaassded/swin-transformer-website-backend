# API Manual (only the more involved APIs are explained)

## Endpoint overview

Routes are defined in [`swinTransformer/urls.py`](../urls.py).

| Route                                          | View                                       | Purpose                                                       |
|------------------------------------------------|--------------------------------------------|---------------------------------------------------------------|
| `login/`, `logout/`, `logup/`                  | `user_view`                                | Log in, log out, register                                     |
| `verify/<verification_token>`                  | `user_view.verify_user_emil`               | Confirm that an e-mail address belongs to the user            |
| `upload/`                                      | `image_view.upload_file`                   | **Segment an uploaded image with Swin Transformer**           |
| `delete/`                                      | `image_view.deleteImage`                   | Delete the image pair with the given id                       |
| `download/<filename>/`                         | `image_view.download_image`                | Download a segmented image                                    |
| `getImage/<page_number>/<lines_per_page>`      | `image_view.get_images_by_page`            | Paginated history (server-side paging)                        |
| `getPageNumber/`                               | `image_view.get_max_page_number`           | Total number of history pages for the user                    |
| `searchImage/`                                 | `image_view.get_images_by_token_and_page`  | [Fuzzy search](fuzzy-search.md) of the history by keyword and page |

---

### upload_file (the actual work is done by `process_image`)

1. Read the image the user uploaded (form field `picture`) and pass it to the Swin Transformer
   model script, which produces the segmented image.
2. Create the matching database records (`OriginalImage` and `SegmentedImage`) so the result
   appears in the user's history.
3. Store both the original and the segmented image in the Nginx server's image directory. Images
   are passed around as **URLs**, never as raw image data.
4. Return the database id of the image pair to the frontend. The frontend can use the id to query
   the image pair and get the URLs it needs to show the images to the user.

**Response**

```json
{
  "isSuccessful": true,
  "source_image_id": 42,
  "source_image_url": "http://localhost/images/street.jpg",
  "segmented_image_url": "http://localhost/images/street_segmented_1700000000.123456.jpg",
  "message": "description of what happened"
}
```

| Field                 | Meaning                                                               |
|-----------------------|-----------------------------------------------------------------------|
| `isSuccessful`        | Whether processing succeeded                                          |
| `source_image_id`     | Id of the image pair, used later to query or delete it                |
| `source_image_url`    | URL of the image the user uploaded                                    |
| `segmented_image_url` | URL of the segmented image                                            |
| `message`             | Human-readable description, set on errors                             |

**What happens in the model step**

`process_image(file_name)` in [`tools/utils.py`](../tools/utils.py):

1. Builds the output name `<name>_segmented_<timestamp>.<ext>` in the Nginx image directory.
2. Runs `python swin_transformer.py --checkpoint … --img … --outfile …` in a subprocess from
   `swinTransformer/utils/swinTransformer/demo` (see [Running inference](swin-inference.md#4-how-the-backend-calls-the-model)).
3. Returns the segmented image URL when the script exits with code `0`, or an empty string
   otherwise.

**Error messages**

| `message`                                   | Cause                                                                                       |
|---------------------------------------------|---------------------------------------------------------------------------------------------|
| `io error on server`                        | The upload could not be written to the Nginx image directory                                |
| `something wrong in swin Transformer model` | The model script exited with a non-zero code. Run it by hand to see the traceback ([troubleshooting](swin-inference.md#6-troubleshooting)) |
| `something wrong in data base`              | Creating the `OriginalImage` / `SegmentedImage` record failed                               |

**Note:** the request blocks until the model finishes, and the model is reloaded on every call.
The plan to move this into a background worker is in [swin-celery.md](swin-celery.md).
