#!/usr/bin/env python3
# coding: utf-8

import os
import sys
import shutil
sys.path.append('../..')

os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # change to chosen GPU to use, nothing if work on CPU

import numpy as np

from deepsphere import models
from ClimateDataLoader import IcosahedronDataset
from pygsp.graphs import SphereIcosahedron as icosahedron_graph

from sklearn.metrics import average_precision_score
from sklearn.preprocessing import label_binarize


def accuracy(pred_cls, true_cls, nclass=3):
    accu = []
    tot_int = 0
    tot_cl = 0
    for i in range(nclass):
        intersect = np.sum(((pred_cls == i) * (true_cls == i)))
        thiscls = np.sum(true_cls == i)
        accu.append(intersect / thiscls * 100)
        tot_int += intersect
        tot_cl += thiscls
    return np.array(accu), np.mean(accu) # , tot_int/tot_cl * 100


def average_precision(score_cls, true_cls, nclass=3):
    score = score_cls
    true = label_binarize(true_cls.reshape(-1), classes=[0, 1, 2])
    score = score.reshape(-1, nclass)
    return average_precision_score(true, score, None)


if __name__ == '__main__':
    sampling = 'icosahedron'
    filepath = 'results_icosahedron_local'
    
    path = '../../data/Climate/'
    g = icosahedron_graph(5)
    icolong, icolat = np.rad2deg(g.long), np.rad2deg(g.lat)
    del g
    
    training = IcosahedronDataset(path+'data_5_all/', 'train')
    validation = IcosahedronDataset(path+'data_5_all/', 'val')
    test = IcosahedronDataset(path+'data_5_all/', 'test')
    
    EXP_NAME = 'Climate_pooling_{}_7layers_k4_initial'.format(sampling)
    
    # Cleanup before running again.
    shutil.rmtree('../../summaries/{}/'.format(EXP_NAME), ignore_errors=True)
    shutil.rmtree('../../checkpoints/{}/'.format(EXP_NAME), ignore_errors=True)
    
    import tensorflow as tf
    params = {'nsides': [5, 5, 4, 3, 2, 1, 0, 0],
              'F': [32, 64, 128, 256, 512, 512, 512],
              'K': [4]*7,
              'batch_norm': [True]*7}
    params['sampling'] = sampling
    params['dir_name'] = EXP_NAME
    params['num_feat_in'] = 16  # x_train.shape[-1]
    params['conv'] = 'chebyshev5'
    params['pool'] = 'average'
    params['activation'] = 'relu'
    params['statistics'] = None  # 'mean'
    params['regularization'] = 0
    params['dropout'] = 1
    params['num_epochs'] = 30  # Number of passes through the training data.
    params['batch_size'] = 8
    params['scheduler'] = lambda step: tf.train.exponential_decay(1e-3, step, decay_steps=2000, decay_rate=1)
    params['optimizer'] = lambda lr: tf.train.AdamOptimizer(lr, beta1=0.9, beta2=0.999, epsilon=1e-8)
    n_evaluations = 30
    params['eval_frequency'] = int(params['num_epochs'] * (training.N) / params['batch_size'] / n_evaluations)
    params['M'] = []
    params['Fseg'] = 3 # np.max(labels_train).astype(int)+1
    params['dense'] = True
    params['weighted'] = False
    params['tf_dataset'] = training.get_tf_dataset(params['batch_size'])
    
    model = models.deepsphere(**params)
    
    print("the number of parameters in the model is: {:,}".format(model.get_nbr_var()))
    
    acc_val, loss_val, loss_train, t_step, t_batch = model.fit(training, validation, use_tf_dataset=True, cache='TF')
    
    probabilities, _, _ = model.probs(test, 3, cache='TF')
    predictions, labels_test, loss = model.predict(test, cache='TF')
    
    AP = average_precision(probabilities, labels_test)
    mAP = np.mean(AP[1:])
    acc, macc = accuracy(predictions, labels_test)
    
    if os.path.isfile(filepath+'.npz'):
        file = np.load(filepath+'.npz')
        tb = file['tbatch'].tolist()
        avprec = file['AP'].tolist()
        accuracy = file['acc'].tolist()
    else:
        tb = []
        avprec = []
        accuracy = []
    tb.append(t_batch)
    avprec.append([*AP, mAP])
    accuracy.append([*acc, macc])
    np.savez(filepath, AP=avprec, acc=accuracy, tbatch=tb)
    
    print("Test Set: AP {:.4f}, {:.4f}, mean: {:.4f}; Accuracy {:.4f}, {:.4f}, {:.4f}, mean: {:.4f}; t_inference {:.4f}".format(
               *(AP[1:]), mAP, *acc, macc, t_batch/params['batch_size']*1000))
