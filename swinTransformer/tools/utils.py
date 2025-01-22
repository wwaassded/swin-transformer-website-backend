import subprocess
import time

from swin import settings
from swinTransformer.tools.constant import nginx_image_dir, nginx_image_url_root
from swinTransformer.tools.constant import swin_transformer_checkpoint, swin_transformer_working_dir


def process_image(original_img_name: str) -> str:
    local_original_img_name = nginx_image_dir + original_img_name
    file_name = original_img_name.split('.')
    local_segmented_img_file_name = file_name[0] + '_segmented' + f'_{time.time()}'+ '.' + file_name[1]
    local_segmented_img_name = nginx_image_dir + local_segmented_img_file_name
    code = swinTransformerHandler(local_original_img_name, local_segmented_img_name)
    if code == 0:
        segmented_image_url = nginx_image_url_root + local_segmented_img_file_name
        return segmented_image_url
    else:
        return ''


def swinTransformerHandler(original_image: str, output_image: str) -> int:
    result = subprocess.run(['python',
                             settings.SWIN_TRANSFORMER,
                             '--checkpoint', swin_transformer_checkpoint,
                             '--img', original_image,
                             '--outfile', output_image],
                            cwd=swin_transformer_working_dir
                            )
    return result.returncode
