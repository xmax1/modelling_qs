
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''

import tensorflow as tf
import numpy as np

n_samples = 10
n_electrons = 4

def generate_pairwise_masks(n_electrons, n_pairwise, n_spin_up, n_spin_down, n_pairwise_features):
    ups = np.ones(n_electrons, dtype=np.bool)
    ups[n_spin_up:] = False
    downs = ~ups

    spin_up_mask = []
    spin_down_mask = []

    mask = np.zeros((n_electrons, n_electrons), dtype=np.bool)

    for electron in range(n_electrons):
        mask_up = np.copy(mask)  # each of these indicates how to mask out the pairwise terms
        mask_up[electron, :] = ups
        spin_up_mask.append(mask_up)

        mask_down = np.copy(mask)
        mask_down[electron, :] = downs
        spin_down_mask.append(mask_down)

    spin_up_mask = tf.convert_to_tensor(spin_up_mask, dtype=tf.bool)
    # (n_samples, n_electrons, n_electrons, n_pairwise_features)
    spin_up_mask = tf.reshape(spin_up_mask, (1, n_electrons, n_pairwise, 1))
    spin_up_mask = tf.tile(spin_up_mask, (1, 1, 1, n_pairwise_features))

    spin_down_mask = tf.convert_to_tensor(spin_down_mask, dtype=tf.bool)
    spin_down_mask = tf.reshape(spin_down_mask, (1, n_electrons, n_pairwise, 1))
    spin_down_mask = tf.tile(spin_down_mask, (1, 1, 1, n_pairwise_features))

    return spin_up_mask, spin_down_mask

w = tf.random.normal((4, 10))

mask, _ = generate_pairwise_masks(n_electrons, n_electrons**2, 2, 2, 4)

re = tf.random.normal((n_samples, n_electrons, 3))

# grads working
with tf.GradientTape() as g:
    g.watch(re)
    re1 = tf.expand_dims(re, 2)
    re2 = tf.transpose(re1, perm=(0, 2, 1, 3))
    ee_vec = re1 - re2
    ee_vec = tf.reshape(ee_vec, (-1, n_electrons ** 2, 3))
    ee_dist = tf.norm(ee_vec, keepdims=True, axis=-1)

    pairwise = tf.concat((ee_vec, ee_dist), -1)

    y = pairwise @ w

z = g.gradient(y, pairwise)

# print(z)


def laplacian(model, r_electrons):
    n_electrons = r_electrons.shape[1]
    r_electrons = tf.reshape(r_electrons, (-1, n_electrons*3))
    r_s = [r_electrons[..., i] for i in range(r_electrons.shape[-1])]
    with tf.GradientTape(True) as g:
        [g.watch(r) for r in r_s]
        r_electrons = tf.stack(r_s, -1)
        r_electrons = tf.reshape(r_electrons, (-1, n_electrons, 3))
        with tf.GradientTape(True) as gg:
            gg.watch(r_electrons)
            log_phi, _, _, _, _ = model(r_electrons)
        dlogphi_dr = gg.gradient(log_phi, r_electrons)
        dlogphi_dr = tf.reshape(dlogphi_dr, (-1, n_electrons*3))
        grads = [dlogphi_dr[..., i] for i in range(dlogphi_dr.shape[-1])]
    d2logphi_dr2 = tf.stack([g.gradient(grad, r) for grad, r in zip(grads, r_s)], -1)
    return dlogphi_dr**2, d2logphi_dr2

@tf.custom_gradient
def safe_norm(x):
    norm = tf.norm(x, keepdims=True, axis=-1)
    def grad(dy):
        g = x / tf.sqrt(tf.reduce_sum(x**2))
        g = tf.where(tf.math.is_nan(g), tf.zeros_like(g), g)
        return dy*g
    return norm, grad

n = 100
from time import time

t0 = time()
for _ in range(n):
    n_electrons = re.shape[1]
    re = tf.reshape(re, (-1, n_electrons*3))
    r_s = [re[..., i] for i in range(re.shape[-1])]
    with tf.GradientTape(True) as g:
        [g.watch(r) for r in r_s]
        re = tf.stack(r_s, -1)
        re = tf.reshape(re, (-1, n_electrons, 3))
        with tf.GradientTape(True) as gg:
            gg.watch(re)

            # model
            re1 = tf.expand_dims(re, 2)
            re2 = tf.transpose(re1, perm=(0, 2, 1, 3))
            ee_vec = re1 - re2

            # ee_dist = tf.norm(ee_vec, keepdims=True, axis=-1)
            ee_dist = safe_norm(ee_vec)
            pairwise = tf.concat((ee_vec, ee_dist), -1)
            pairwise = tf.reshape(pairwise, (-1, n_electrons**2, 4))

            # ops
            sum_pairwise = tf.tile(tf.expand_dims(pairwise, 1), (1, n_electrons, 1, 1))
            replace = tf.zeros_like(sum_pairwise)
            # up
            sum_pairwise_up = tf.where(mask, sum_pairwise, replace)
            e_masked = tf.reduce_sum(sum_pairwise_up, 2) / 2

            log_phi = e_masked @ w

        dlogphi_dr = gg.gradient(log_phi, re)
        dlogphi_dr = tf.reshape(dlogphi_dr, (-1, n_electrons * 3))
        grads = [dlogphi_dr[..., i] for i in range(dlogphi_dr.shape[-1])]
    d2logphi_dr2 = tf.stack([g.gradient(grad, r) for grad, r in zip(grads, r_s)], -1)
print(time() - t0)

t0 = time()
for _ in range(n):
    n_electrons = re.shape[1]
    re = tf.reshape(re, (-1, n_electrons*3))
    r_s = [re[..., i] for i in range(re.shape[-1])]
    with tf.GradientTape(True) as g:
        [g.watch(r) for r in r_s]
        re = tf.stack(r_s, -1)
        re = tf.reshape(re, (-1, n_electrons, 3))
        with tf.GradientTape(True) as gg:
            gg.watch(re)

            # model
            re1 = tf.expand_dims(re, 2)
            re2 = tf.transpose(re1, perm=(0, 2, 1, 3))
            ee_vec = re1 - re2

            ee_dist = tf.norm(ee_vec, keepdims=True, axis=-1)
            # ee_dist = safe_norm(ee_vec)
            pairwise = tf.concat((ee_vec, ee_dist), -1)
            pairwise = tf.reshape(pairwise, (-1, n_electrons**2, 4))

            # ops
            sum_pairwise = tf.tile(tf.expand_dims(pairwise, 1), (1, n_electrons, 1, 1))
            replace = tf.zeros_like(sum_pairwise)
            # up
            sum_pairwise_up = tf.where(mask, sum_pairwise, replace)
            e_masked = tf.reduce_sum(sum_pairwise_up, 2) / 2

            log_phi = e_masked @ w

        dlogphi_dr = gg.gradient(log_phi, re)
        dlogphi_dr = tf.reshape(dlogphi_dr, (-1, n_electrons * 3))
        grads = [dlogphi_dr[..., i] for i in range(dlogphi_dr.shape[-1])]
    d2logphi_dr2 = tf.stack([g.gradient(grad, r) for grad, r in zip(grads, r_s)], -1)
print(time() - t0)

