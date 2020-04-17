


# The functions below are proxies for the actor

import tensorflow as tf
from energy.energy_utils import clip
import ray

# sampling
def burn(models, n_burns):
    for _ in range(n_burns):
        [model.burn.remote() for model in models]


def burn_pretrain(models, n_burns):
    for _ in range(n_burns):
        [model.burn_pretrain.remote() for model in models]


# pretraining
def get_pretrain_grads(models):
    grads = ray.get([model.get_pretrain_grads.remote() for model in models])
    new_grads = []
    for i in range(len(grads[0])):
        grad = tf.stack([grad[i] for grad in grads])
        grad = tf.reduce_sum(grad, axis=0)
        new_grads.append(grad)
    return new_grads


def update_weights_pretrain(models, grads):
    grad_id = ray.put(grads)
    models[0].update_weights_pretrain.remote(grad_id)
    weights_id = models[0].get_weights.remote()
    [model.set_weights.remote(weights_id) for model in models[1:]]


# training
def get_grads(models):
    grads = ray.get([model.get_grads.remote() for model in models])
    new_grads = []
    for layer_id in range(len(grads[0])):
        grads_layer = tf.reduce_mean(tf.stack([grad[layer_id] for grad in grads]), axis=0)
        new_grads.append(grads_layer)
    return new_grads


def update_weights_optimizer(models, grads):
    grad_id = ray.put(grads)
    models[0].update_weights.remote(grad_id)
    weights_id = models[0].get_weights.remote()
    [model.set_weights.remote(weights_id) for model in models[1:]]
    return


# kfac
def get_grads_and_maa_and_mss(models, layers):
    data = ray.get([model.get_grads_and_maa_and_mss.remote() for model in models])
    grads = [d[0] for d in data]
    m_aa = [d[1] for d in data]
    m_ss = [d[2] for d in data]

    mean_g = []
    mean_m_aa = {}
    mean_m_ss = {}
    for j, name in enumerate(layers):
        mean_g.append(tf.reduce_mean(tf.stack([g[j] for g in grads]), axis=0))
        maa = (tf.reduce_mean(tf.stack([ma[name] for ma in m_aa]), axis=0))
        mss = (tf.reduce_mean(tf.stack([ms[name] for ms in m_ss]), axis=0))
        # enforce symmetry (there may be numerical errors)
        maa = (tf.linalg.matrix_transpose(maa) + maa) / 2.
        mss = (tf.linalg.matrix_transpose(mss) + mss) / 2.
        mean_m_aa[name] = maa
        mean_m_ss[name] = mss

    return mean_g, mean_m_aa, mean_m_ss


def step_forward(models, updates):
    updates_id = ray.put(updates)
    models[0].step_forward.remote(updates_id)
    weights_id = models[0].get_weights.remote()
    [model.set_weights.remote(weights_id) for model in models[1:]]
    return


# energy
def get_energy(models):
    e_locs = ray.get([model.get_energy.remote() for model in models])
    e_loc = tf.concat(e_locs, axis=0)
    e_mean = tf.reduce_mean(e_loc)
    e_std = tf.math.reduce_std(e_loc)
    return e_loc, e_mean, e_std


def get_energy_and_center(models, iteration):
    e_loc, e_mean, e_std = get_energy(models)
    e_loc_clipped = clip(e_loc, iteration)
    e_loc_centered = e_loc_clipped - tf.reduce_mean(e_loc_clipped)
    return e_loc_centered, e_mean, e_loc, e_std




# utils
def get_info(models):
    info = ray.get([model.get_info.remote() for model in models])
    amplitudes = [lst[0] for lst in info]
    acceptance = tf.reduce_mean([lst[1] for lst in info])
    samples = [lst[2] for lst in info]
    e_loc = tf.concat([lst[3] for lst in info], axis=0)
    return amplitudes, acceptance, samples, e_loc
