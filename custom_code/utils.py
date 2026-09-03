import numpy as np

def get_zeropoint():
    """
    Function to set the photometric zeropoint used to convert between magnitudes and flux
    """

    return 25.0

def flux_to_mag(flux, flux_err, exp_time=None):
    """Function to convert the flux of a star from its fitted PSF model
    and its uncertainty onto the magnitude scale.

    :param float flux: Total star flux
    :param float flux_err: Uncertainty in star flux
    :param float exp_time: [optional] Exposure time in s

    Input flux, flux_err can be scalar values or arrays.  If an exposure time is given,
    the fluxes and uncertainties will be scaled by the exposure time.

    Returns:

    :param float mag: Measured star magnitude
    :param float flux_mag: Uncertainty in measured magnitude
    :param float flux: Total flux, scaled by the exposure time if given
    :param float flux_err: Uncertainty on total flux, scaled by the exposure
                            time, if given
    """

    def flux2mag(ZP, flux):

        return ZP - 2.5 * np.log10(flux)

    def fluxerr2magerr(flux, flux_err):

        return (2.5 / np.log(10.0)) * flux_err / flux

    ZP = get_zeropoint()

    # Case if input is a scaler value
    if type(flux) == float or type(flux) == np.float64:
        if flux < 0.0 or flux_err < 0.0:

            mag = 0.0
            mag_err = 0.0

        else:

            if exp_time:
                frac_err = flux_err / flux
                flux = flux / exp_time
                flux_err = flux * frac_err

            mag = flux2mag(ZP, flux)
            mag_err = fluxerr2magerr(flux, flux_err)

    # Case if input is an array (which we assume is a numpy array rather than
    # a list etc), which may have some zero entries
    else:
        mag = np.zeros(len(flux))
        mag_err = np.zeros(len(flux_err))

        mask = (flux > 0.0) & (flux_err > 0.0)
        if exp_time:
            frac_err = np.zeros(len(flux))

            frac_err[mask] = flux_err[mask] / flux[mask]
            flux[mask] = flux[mask] / exp_time
            flux_err[mask] = flux[mask] * frac_err[mask]

        mag[mask] = flux2mag(ZP, flux[mask])
        mag_err[mask] = fluxerr2magerr(flux[mask], flux_err[mask])

    return mag, mag_err, flux, flux_err


def mag_to_flux(mag, mag_err):
    """Function to convert the flux of a star from its fitted PSF model
    and its uncertainty onto the magnitude scale.

    :param float flux: Total star flux
    :param float flux_err: Uncertainty in star flux

    Returns:

    :param float mag: Measured star magnitude
    :param float flux_mag: Uncertainty in measured magnitude
    :param float flux: Total flux, scaled by the exposure time if given
    :param float flux_err: Uncertainty on total flux, scaled by the exposure
                            time, if given
    """

    ZP = get_zeropoint()

    flux = 10 ** ((mag - ZP) / -2.5)

    ferr = mag_err / (2.5 * np.log10(np.e)) * flux

    return flux, ferr
