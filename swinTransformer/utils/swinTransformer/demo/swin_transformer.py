from argparse import ArgumentParser

from mmseg.apis import inference_segmentor, init_segmentor, show_result_pyplot
from mmseg.core.evaluation import get_palette


def main():
    parser = ArgumentParser()
    parser.add_argument('--outfile', default='', help='output image')
    parser.add_argument('--img', default='', help='Image file')
    parser.add_argument('--config', default='../configs/swin/upernet_swin_tiny_patch4_window7_512x512_160k_ade20k.py',
                        help='Config file')
    parser.add_argument('--checkpoint', default='', help='Checkpoint file')
    parser.add_argument(
        '--device', default='cuda:0', help='Device used for inference')
    parser.add_argument(
        '--palette',
        default='ade20k',
        help='Color palette used for segmentation map')
    args = parser.parse_args()

    # build the model from a config file and a checkpoint file
    model = init_segmentor(args.config, args.checkpoint, device=args.device)
    # test a single image
    result = inference_segmentor(model, args.img)
    # show the results
    show_result_pyplot(model, args.img, result, args.outfile, get_palette(args.palette))


if __name__ == '__main__':
    main()
