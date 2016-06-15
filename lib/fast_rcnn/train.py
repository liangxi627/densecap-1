# --------------------------------------------------------
# Fast R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick
# --------------------------------------------------------

"""Train a Fast R-CNN network."""

import caffe
from fast_rcnn.config import cfg
import roi_data_layer.roidb as rdl_roidb
from utils.timer import Timer
from utils.debug import softmax
import numpy as np
import os

from caffe.proto import caffe_pb2
import google.protobuf as pb2
DEBUG=False

class SolverWrapper(object):
    """A simple wrapper around Caffe's solver.
    This wrapper gives us control over he snapshotting process, which we
    use to unnormalize the learned bounding-box regression weights.
    """

    def __init__(self, solver_prototxt, roidb, output_dir,
                 pretrained_model=None):
        """Initialize the SolverWrapper."""
        self.output_dir = output_dir

        if (cfg.TRAIN.HAS_RPN and cfg.TRAIN.BBOX_REG and
            cfg.TRAIN.BBOX_NORMALIZE_TARGETS):
            # RPN can only use precomputed normalization because there are no
            # fixed statistics to compute a priori
            assert cfg.TRAIN.BBOX_NORMALIZE_TARGETS_PRECOMPUTED

        if cfg.TRAIN.BBOX_REG:
            print 'Computing bounding-box regression targets...'
            self.bbox_means, self.bbox_stds = \
                    rdl_roidb.add_bbox_regression_targets(roidb)
            print 'done'

        self.solver = caffe.SGDSolver(solver_prototxt)
        if pretrained_model is not None:
            print ('Loading pretrained model '
                   'weights from {:s}').format(pretrained_model)
            self.solver.net.copy_from(pretrained_model)

        self.solver_param = caffe_pb2.SolverParameter()
        with open(solver_prototxt, 'rt') as f:
            pb2.text_format.Merge(f.read(), self.solver_param)

        self.solver.net.layers[0].set_roidb(roidb)

    def snapshot(self):
        """Take a snapshot of the network after unnormalizing the learned
        bounding-box regression weights. This enables easy use at test-time.
        """
        net = self.solver.net
        # This is a stupid check, disabled temperally
        scale_bbox_params = False #(cfg.TRAIN.BBOX_REG and
                             #cfg.TRAIN.BBOX_NORMALIZE_TARGETS and
                             #net.params.has_key('bbox_pred'))

        if scale_bbox_params:
            # save original values
            orig_0 = net.params['bbox_pred'][0].data.copy()
            orig_1 = net.params['bbox_pred'][1].data.copy()

            # scale and shift with bbox reg unnormalization; then save snapshot
            net.params['bbox_pred'][0].data[...] = \
                    (net.params['bbox_pred'][0].data *
                     self.bbox_stds[:, np.newaxis])
            net.params['bbox_pred'][1].data[...] = \
                    (net.params['bbox_pred'][1].data *
                     self.bbox_stds + self.bbox_means)

        infix = ('_' + cfg.TRAIN.SNAPSHOT_INFIX
                 if cfg.TRAIN.SNAPSHOT_INFIX != '' else '')
        filename = (self.solver_param.snapshot_prefix + infix +
                    '_iter_{:d}'.format(self.solver.iter) + '.caffemodel')
        filename = os.path.join(self.output_dir, filename)

        net.save(str(filename))
        print 'Wrote snapshot to: {:s}'.format(filename)

        if scale_bbox_params:
            # restore net to original state
            net.params['bbox_pred'][0].data[...] = orig_0
            net.params['bbox_pred'][1].data[...] = orig_1
        return filename

    def train_model(self, max_iters):
        """Network training loop."""
        last_snapshot_iter = -1
        timer = Timer()
        model_paths = []
        while self.solver.iter < max_iters:
            
            
            # Make one SGD update
            timer.tic()
            self.solver.step(1)
            timer.toc()
            if DEBUG:
                
                
                #print self.solver.net.blobs['conv3_3'].diff
                print self.solver.net.params['conv3_3'][0].data
                # fc7_diff =self.solver.net.blobs['fc7_reshape'].diff
                # print 'fc7 diff samples'
                # print fc7_diff[0,0,:]
                # print fc7_diff[0,-1,:]
                # bbox_pred =self.solver.net.blobs['bbox_pred'].data
                # bbox_pred_d =self.solver.net.blobs['bbox_pred'].diff
                # print 'bbox pred samples'
                # print bbox_pred[:,0,:]
                # print bbox_pred[:,-1,:]
                # print 'bbox pred diff samples'
                # print bbox_pred_d[:,0,:]
                # print bbox_pred_d[:,-1,:]

               

                # bbox_target =self.solver.net.blobs['bbox_targets'].data
                # print 'bbox target samples'
                # print bbox_target[0,:]
                # print bbox_target[-1,:]
                # bbox_weights = self.solver.net.blobs['bbox_inside_weights'].data
                # print 'bbox inside weights'
                # print bbox_weights[0,:]
                # print bbox_weights[-1,:]
              
            if self.solver.iter % (10 * self.solver_param.display) == 0:
                print 'speed: {:.3f}s / iter'.format(timer.average_time)
            #if self.solver_param.test_interval>0 and self.solver.iter % self.solver_param.test_interval == 0:

            if self.solver.iter % cfg.TRAIN.SNAPSHOT_ITERS == 0:
                last_snapshot_iter = self.solver.iter
                model_paths.append(self.snapshot())

        if last_snapshot_iter != self.solver.iter:
            model_paths.append(self.snapshot())
        return model_paths
    
    def vis_regions(self, im, regions, iter_n, save_path='debug'):
        """Visual debugging of detections by saving images with detected bboxes."""
        import cv2
        if not os.path.exists(save_path):
                    os.makedirs(save_path)
        mean_values = np.array([[[ 102.9801,  115.9465,  122.7717]]])
        im = im + mean_values #offset to original values


        for i in xrange(len(regions)):
            bbox = regions[i, :4]
            region_id = regions[i,4]
            if region_id == 0:
                continue
            caption = self.sentence(self._all_phrases[region_id])

            im_new = np.copy(im)     
            cv2.rectangle(im_new, (bbox[0],bbox[1]), (bbox[2],bbox[3]), (0,0,255), 2)
            cv2.imwrite('%s/%d_%s.jpg' % (save_path, iter_n, caption), im_new)
    def sentence(self, vocab_indices):
        # consider <eos> tag with id 0 in vocabulary
        sentence = ' '.join([self._vocab[i] for i in vocab_indices])
        return sentence

def get_training_roidb(imdb):
    """Returns a roidb (Region of Interest database) for use in training."""
    if cfg.TRAIN.USE_FLIPPED:
        print 'Appending horizontally-flipped training examples...'
        imdb.append_flipped_images()
        print 'done'

    print 'Preparing training data...'
    rdl_roidb.prepare_roidb(imdb)
    print 'done'

    return imdb.roidb

def filter_roidb(roidb):
    """Remove roidb entries that have no usable RoIs."""

    def is_valid(entry):
        # Valid images have:
        #   (1) At least one foreground RoI OR
        #   (2) At least one background RoI
        overlaps = entry['max_overlaps']
        # find boxes with sufficient overlap
        fg_inds = np.where(overlaps >= cfg.TRAIN.FG_THRESH)[0]
        # Select background RoIs as those within [BG_THRESH_LO, BG_THRESH_HI)
        bg_inds = np.where((overlaps < cfg.TRAIN.BG_THRESH_HI) &
                           (overlaps >= cfg.TRAIN.BG_THRESH_LO))[0]
        # image is only valid if such boxes exist
        valid = len(fg_inds) > 0 or len(bg_inds) > 0
        return valid

    num = len(roidb)
    filtered_roidb = [entry for entry in roidb if is_valid(entry)]
    num_after = len(filtered_roidb)
    print 'Filtered {} roidb entries: {} -> {}'.format(num - num_after,
                                                       num, num_after)
    return filtered_roidb

def train_net(solver_prototxt, roidb, output_dir,
              pretrained_model=None, max_iters=40000):
    """Train a Fast R-CNN network."""

    roidb = filter_roidb(roidb)
    sw = SolverWrapper(solver_prototxt, roidb, output_dir,
                       pretrained_model=pretrained_model)

    print 'Solving...'
    model_paths = sw.train_model(max_iters)
    print 'done solving'
    return model_paths