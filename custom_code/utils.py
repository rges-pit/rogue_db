import numpy as np
from django.core.files.base import ContentFile
import io


def replace_image_file(file_field, filename, content):
    """
    Save content as the picture of an image field of an instance (its FieldFile, such as an event's
    thumbnail), overwriting any existing file.

    :param file_field: the FieldFile, e.g. event.thumbnail
    :param filename: the name for the file, without the field's upload_to directory
    :param content: a File, such as django.core.files.base.ContentFile, of the picture
    """
    storage = file_field.storage
    old_name = file_field.name or None

    new_name = file_field.field.generate_filename(file_field.instance, filename)
    if storage.exists(new_name):
        storage.delete(new_name)

    file_field.save(filename, content, save=False)

    if old_name and old_name != file_field.name and storage.exists(old_name):
        storage.delete(old_name)


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


def store_array_as_np(arr, file_name, model_field):
    """
    Function to output a Numpy array to file, compatible with different storage types

    file_name should be just the desired file name without a path, e.g. RMDC26_000001_lightcurve.npy
    """
    buffer = io.BytesIO()
    np.save(buffer, arr, allow_pickle=False)

    file_content = ContentFile(buffer.getvalue())
    replace_image_file(model_field, file_name, file_content)

def load_array_from_file(file_field):
    """
    Function to load a numpy array from any file storage

    The file field is a model field that references a file, such as eventmodel.mcmc_chains
    """

    with file_field.open('rb') as f:
        return np.load(io.BytesIO(f.read()), allow_pickle=False)
