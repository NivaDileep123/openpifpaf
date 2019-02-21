"""Webcam demo application.

Example command:
    python -m pifpaf.webcam \
        --checkpoint outputs/resnet101-pif-paf-rsmooth0.5-181121-170119.pkl \
        --src http://128.179.139.21:8080/video \
        --seed-threshold=0.3 \
        --scale 0.2 \
        --connection-method=max
"""


import argparse
import matplotlib.pyplot as plt
import matplotlib.animation
import time

import numpy as np
import torch

import cv2
from .network import nets
from . import decoder, show, transforms


class Visualizer(object):
    def __init__(self, processor, args):
        self.processor = processor
        self.args = args

    def __call__(self, first_image, fig_width=4.0, **kwargs):
        if 'figsize' not in kwargs:
            kwargs['figsize'] = (fig_width, fig_width * first_image.shape[0] / first_image.shape[1])

        fig = plt.figure(**kwargs)
        ax = plt.Axes(fig, [0.0, 0.0, 1.0, 1.0])
        ax.set_axis_off()
        ax.set_xlim(0, first_image.shape[1])
        ax.set_ylim(first_image.shape[0], 0)
        fig.add_axes(ax)
        mpl_im = ax.imshow(first_image)
        fig.show()

        while True:
            image, all_fields = yield
            keypoint_sets, scores = self.processor.keypoint_sets(all_fields)

            draw_start = time.time()
            while ax.lines:
                del ax.lines[0]
            mpl_im.set_data(image)
            if self.args.colored_connections:
                show.keypoints(ax, keypoint_sets, show_box=False,
                               markersize=1,
                               color_connections=True, linewidth=6)
            else:
                show.keypoints(ax, keypoint_sets, show_box=False)
            fig.canvas.draw()
            print('draw', time.time() - draw_start)
            plt.pause(0.01)

        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    nets.cli(parser)
    decoder.cli(parser, force_complete_pose=False, instance_threshold=0.05)
    parser.add_argument('--colored-connections', default=False, action='store_true',
                        help='use colored connections to draw poses')
    parser.add_argument('--disable-cuda', action='store_true',
                        help='disable CUDA')
    parser.add_argument('--source', default=0,
                        help='OpenCV source url. Integer for webcams. Or ipwebcam streams.')
    parser.add_argument('--scale', default=0.1, type=float,
                        help='input image scale factor')
    args = parser.parse_args()

    # check whether source should be an int
    if len(args.source) == 1:
        args.source = int(args.source)

    # add args.device
    args.device = torch.device('cpu')
    if not args.disable_cuda and torch.cuda.is_available():
        args.device = torch.device('cuda')

    # load model
    model, _ = nets.factory(args)
    model = model.to(args.device)
    processors = decoder.factory(args, model)

    last_loop = time.time()
    capture = cv2.VideoCapture(args.source)

    visualizers = None
    while True:
        _, image_original = capture.read()
        image = cv2.resize(image_original, None, fx=args.scale, fy=args.scale)
        print('resized image size: {}'.format(image.shape))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        if visualizers is None:
            visualizers = [Visualizer(p, args)(image) for p in processors]
            for v in visualizers:
                v.send(None)

        start = time.time()
        processed_image_cpu = transforms.image_transform(image.copy())
        processed_image = processed_image_cpu.contiguous().to(args.device, non_blocking=True)
        print('preprocessing time', time.time() - start)

        all_fields = processors[0].fields(processed_image.float())
        for v in visualizers:
            v.send((image, all_fields))

        print('loop time = {:.3}s, FPS = {:.3}'.format(
            time.time() - last_loop, 1.0 / (time.time() - last_loop)))
        last_loop = time.time()


if __name__ == '__main__':
    main()
