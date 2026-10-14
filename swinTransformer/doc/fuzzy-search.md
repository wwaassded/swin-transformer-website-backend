# Fuzzy Search on the History Page

* APIs with similar functionality should behave similarly, so the search API returns the same
  response structure as the regular paginated history API:

```json
JsonResponse: {
                "isSuccessful": whether the request was processed successfully,
                "isCached": whether the data came from the Redis cache,
                "original_id_list": list of ids of the original (pre-segmentation) images,
                "original_images_list": list of the original (pre-segmentation) images,
                "segmented_images_list": list of the segmented images,
                "message": detailed description,
                "isEmpty": whether the result is empty,
                "page_number": total number of pages of search results
            }
```

* The three lists are aligned by index: `original_id_list[i]`, `original_images_list[i]`, and
  `segmented_images_list[i]` all describe the same image pair.
* `page_number` is the number of pages **for this search**, not for the whole history, so the
  frontend can show the right pagination controls while a search is active.
