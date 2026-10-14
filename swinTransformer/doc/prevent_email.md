# How Users Can Avoid Unwanted E-mail

* The frontend keeps a single Boolean flag in a global Pinia store and provides a toggle for it on
  the relevant page.
* The frontend sends this flag with every request. The Django backend reads the Boolean value and
  decides whether to send an e-mail.
* 😕 In some cases an e-mail will always be sent to notify the user, whatever the flag says.

## Open questions

* Which e-mails are mandatory? Account verification at registration is the obvious one. A
  "segmentation finished" notice for long-running jobs (see [swin-celery.md](swin-celery.md)) is a
  good candidate for the optional category.
* Should the preference be stored in the `User` table instead, so it survives a new browser or
  device, rather than living only in frontend state?
