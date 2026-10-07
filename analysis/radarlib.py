"""Shared radar math for the HoloGuard HG-1 design study.

All quantities SI unless suffixed (_db, _dbm, _ghz ...).
"""
import numpy as np

C0 = 299_792_458.0
K_B = 1.380649e-23
T0 = 290.0


def db(x):
    return 10.0 * np.log10(x)


def undb(x_db):
    return 10.0 ** (np.asarray(x_db) / 10.0)


def shnidman_snr_db(pd, pfa, n, swerling):
    """Required single-pulse SNR (dB) for N non-coherently integrated
    looks, Shnidman's empirical equation (accurate to ~0.5 dB).
    swerling: 0 (non-fluctuating), 1, 2, 3, 4."""
    if swerling == 0:
        k = np.inf
    elif swerling == 1:
        k = 1
    elif swerling == 2:
        k = n
    elif swerling == 3:
        k = 2
    elif swerling == 4:
        k = 2 * n
    else:
        raise ValueError("swerling must be 0..4")

    if n < 40:
        alpha = 0.0
    else:
        alpha = 0.25
    eta = np.sqrt(-0.8 * np.log(4 * pfa * (1 - pfa))) + np.sign(pd - 0.5) * np.sqrt(
        -0.8 * np.log(4 * pd * (1 - pd)))
    x_inf = eta * (eta + 2 * np.sqrt(n / 2 + (alpha - 0.25)))
    if np.isinf(k):
        c1 = c2 = 0.0
        c_db = 0.0
    else:
        c1 = (((17.7006 * pd - 18.4496) * pd + 14.5339) * pd - 3.525) / k
        c2 = 1 / k * (np.exp(27.31 * pd - 25.14) + (pd - 0.8) * (
            0.7 * np.log(1e-5 / pfa) + (2 * n - 20) / 80))
        if pd <= 0.872:
            c_db = c1
        else:
            c_db = c1 + c2
    c = 10 ** (c_db / 10)
    x1 = c * x_inf / n
    return 10 * np.log10(x1)


def staring_snr_db(pt_w, g_tx_dbi, g_rx_elem_dbi, n_rx, f_hz, rcs_m2, r_m,
                   t_coh_s, nf_db, loss_db):
    """SNR of one coherent processing interval for a staring (holographic)
    MIMO radar: wide-beam transmit, N_rx-channel coherent digital receive.
    MIMO with N_tx orthogonal transmitters: total radiated power pt_w is
    what counts; virtual array adds resolution, not SNR."""
    lam = C0 / f_hz
    g_rx_dbi = g_rx_elem_dbi + db(n_rx)
    num = (db(pt_w) + g_tx_dbi + g_rx_dbi + db(lam ** 2) + db(rcs_m2) + db(t_coh_s))
    den = (db((4 * np.pi) ** 3) + 4 * db(r_m) + db(K_B * T0) + nf_db + loss_db)
    return num - den


def max_range_m(snr_req_db, **kw):
    """Range at which staring_snr_db == snr_req_db (closed form)."""
    snr_1m = staring_snr_db(r_m=1.0, **kw)
    return 10 ** ((snr_1m - snr_req_db) / 40.0)


def angle_accuracy_deg(beamwidth_deg, snr_db, bias_deg=0.0):
    """Thermal-noise-limited monopulse/DBF angle accuracy (1 sigma) plus a
    fixed calibration bias term added in quadrature."""
    snr = undb(snr_db)
    sig = beamwidth_deg / (1.6 * np.sqrt(2 * snr))
    return np.sqrt(sig ** 2 + bias_deg ** 2)
