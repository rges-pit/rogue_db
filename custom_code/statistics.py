import numpy as np

def calc_tau(chains):

    if len(chains.shape) == 2:
        chain_arr = chains.T
    else:
        chain_arr = chains[:, :, 0].T
    print('CHAIN array: ', chain_arr.shape)

    tau = autocorrelation_time(chain_arr)
    tau_thres = chain_arr.shape[1]/50.0
    print(tau, tau_thres)

    return tau, tau_thres

def autocorrelation_time(chains, c=5.0):
    """
    Function to calculate the integrated autocorrelation time for an MCMC chain,
    following the method described in the documentation for the emcee package:
    https://emcee.readthedocs.io/en/stable/tutorials/autocorr/

    Parameters:
        chains  array   2D array of the chains from an MCMC sampler, [parameters, Nsamples]

    Returns:
        tau     float   Integrated autocorrelation time
    """

    f = np.zeros(chains.shape[1])

    for datum in chains:
        f += autocorr_func_1d(datum)

    f /= len(chains)
    taus = 2.0 * np.cumsum(f) - 1.0
    window = auto_window(taus, c)

    return taus[window]

def next_pow_two(n):
    i = 1
    while i < n:
        i = i << 1
    return i

def autocorr_func_1d(x, norm=True):
    """
    Function to calculate the autocorrelation function
    """

    x = np.atleast_1d(x)
    if len(x.shape) != 1:
        raise ValueError("Invalid dimensions for 1D autocorrelation function")

    n = next_pow_two(len(x))

    # Compute the FFT and then (from that) the auto-correlation function
    f = np.fft.fft(x - np.mean(x), n=2 * n)
    acf = np.fft.ifft(f * np.conjugate(f))[: len(x)].real
    acf /= 4 * n

    # Optionally normalize
    if norm:
        acf /= acf[0]

    return acf

def auto_window(taus, c):
    """Automated windowing procedure following Sokal (1989)"""

    m = np.arange(len(taus)) < c * taus

    if np.any(m):
        return np.argmin(m)

    return len(taus) - 1
