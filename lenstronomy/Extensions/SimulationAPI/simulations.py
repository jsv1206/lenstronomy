from lenstronomy.ImSim.make_image import MakeImage
from lenstronomy.ImSim.lens_model import LensModel
from lenstronomy.ImSim.light_model import LensLightModel, SourceModel
from lenstronomy.Solver.image_positions import ImagePosition
import astrofunc.util as util
from astrofunc.util import Util_class
from astrofunc.LensingProfiles.gaussian import Gaussian

import numpy as np
import copy


class Simulation(object):
    """
    simulation class that querries the major class of lenstronomy
    """
    def __init__(self):
        self.gaussian = Gaussian()
        self.util_class = Util_class()

    def data_configure(self, numPix, deltaPix, exposure_time, sigma_bkg):
        """

        :param numPix: number of pixel (numPix x numPix)
        :param deltaPix: pixel size
        :param exposure_time: exposure time
        :param sigma_bkg: background noise (Gaussian sigma)
        :return:
        """
        mean = 0.  # background mean flux (default zero)
        # 1d list of coordinates (x,y) of a numPix x numPix square grid, centered to zero
        x_grid, y_grid, ra_at_xy_0, dec_at_xy_0, x_at_radec_0, y_at_radec_0, Mpix2coord, Mcoord2pix = util.make_grid_with_coordtransform(numPix=numPix, deltapix=deltaPix, subgrid_res=1)
        # mask (1= model this pixel, 0= leave blanck)
        mask = np.ones_like(x_grid)  # default is model all pixels
        exposure_map = np.ones_like(x_grid) * exposure_time  # individual exposure time/weight per pixel

        kwargs_data = {
            'sigma_background': sigma_bkg, 'mean_background': mean
            , 'deltaPix': deltaPix, 'numPix_xy': (numPix, numPix)
            , 'exp_time': exposure_time, 'exposure_map': exposure_map
            , 'x_coords': x_grid, 'y_coords': y_grid
            , 'x_at_radec_0': x_at_radec_0, 'y_at_radec_0': y_at_radec_0, 'transform_angle2pix': Mcoord2pix
            , 'ra_at_xy_0': ra_at_xy_0, 'dec_at_xy_0': dec_at_xy_0, 'transform_pix2angle': Mpix2coord
            , 'mask': mask
            , 'image_data': np.zeros_like(x_grid)
            }
        return kwargs_data

    def psf_configure(self, psf_type="gaussian", fwhm=1, kernelsize=11, deltaPix=1, truncate=3, kernel=None):
        """

        :param psf_type:
        :param fwhm:
        :param pixel_grid:
        :return:
        """
        # psf_type: 'NONE', 'gaussian', 'pixel'
        # 'pixel': kernel, kernel_large
        # 'gaussian': 'sigma', 'truncate'
        if psf_type == 'gaussian':
            sigma = util.fwhm2sigma(fwhm)
            sigma_axis = sigma/np.sqrt(2)
            x_grid, y_grid = util.make_grid(kernelsize, deltaPix)
            kernel_large = self.gaussian.function(x_grid, y_grid, amp=1., sigma_x=sigma_axis, sigma_y=sigma_axis, center_x=0, center_y=0)
            kernel_large = util.array2image(kernel_large)
            kwargs_psf = {'psf_type': psf_type, 'sigma': sigma, 'truncate': truncate*sigma, 'kernel_large': kernel_large}
        elif psf_type == 'pixel':
            kernel_large = copy.deepcopy(kernel)
            kernel_large = self.util_class.cut_psf(kernel_large, psf_size=kernelsize)
            kernel_small = copy.deepcopy(kernel)
            kernel_small = self.util_class.cut_psf(kernel_small, psf_size=kernelsize)
            kwargs_psf = {'psf_type': "pixel", 'kernel': kernel_small, 'kernel_large': kernel_large}
        elif psf_type == 'NONE':
            kwargs_psf = {'psf_type': 'NONE'}
        else:
            raise ValueError("psf type %s not supported!" % psf_type)
        return kwargs_psf

    def normalize_flux(self, kwargs_options, kwargs_source, kwargs_lens_light, kwargs_else, norm_factor_source=1, norm_factor_lens_light=1, norm_factor_point_source=1.):
        """
        multiplies the surface brightness amplitudes with a norm_factor
        aim: mimic different telescopes photon collection area or colours for different imaging bands
        :param kwargs_source:
        :param kwargs_lens_light:
        :param norm_factor:
        :return:
        """
        lensLightModel = LensLightModel(kwargs_options)
        sourceModel = SourceModel(kwargs_options)
        kwargs_source_updated = copy.deepcopy(kwargs_source)
        kwargs_lens_light_updated = copy.deepcopy(kwargs_lens_light)
        kwargs_else_updated = copy.deepcopy(kwargs_else)
        kwargs_source_updated = sourceModel.lightModel.re_normalize_flux(kwargs_source_updated, norm_factor_source)
        kwargs_lens_light_updated = lensLightModel.lightModel.re_normalize_flux(kwargs_lens_light_updated, norm_factor_lens_light)
        num_images = kwargs_options.get('num_images', 0)
        if num_images > 0 and kwargs_options.get('point_source', False):
                kwargs_else_updated['point_amp'] *= norm_factor_point_source
        return kwargs_source_updated, kwargs_lens_light_updated, kwargs_else_updated

    def im_sim(self, kwargs_options, kwargs_data, kwargs_psf, kwargs_lens, kwargs_source, kwargs_lens_light, kwargs_else, no_noise=False):
        """
        simulate image with solving for the point sources, if option choosen
        :param kwargs_options:
        :param kwargs_data:
        :param kwargs_psf:
        :param kwargs_lens:
        :param kwargs_source:
        :param kwargs_lens_light:
        :param kwargs_else:
        :return:
        """
        lensModel = LensModel(kwargs_options)
        imPos = ImagePosition(lensModel=lensModel)
        if kwargs_options.get('point_source', False):
            deltaPix = kwargs_data['deltaPix']/10.
            numPix = kwargs_data['numPix_xy'][0]*10
            sourcePos_x = kwargs_else['sourcePos_x']
            sourcePos_y = kwargs_else['sourcePos_y']
            x_mins, y_mins = imPos.image_position(sourcePos_x, sourcePos_y, deltaPix, numPix, kwargs_lens, kwargs_else)
            n = len(x_mins)
            mag_list = np.zeros(n)
            for i in range(n):
                potential, alpha1, alpha2, kappa, gamma1, gamma2, mag = lensModel.all(x_mins[i], y_mins[i], kwargs_lens, kwargs_else)
                mag_list[i] = abs(mag)
            kwargs_else['ra_pos'] = x_mins
            kwargs_else['dec_pos'] = y_mins
            kwargs_else['point_amp'] = mag_list * kwargs_else['quasar_amp']

        # update kwargs_else
        image = self.simulate(kwargs_options, kwargs_data, kwargs_psf, kwargs_lens, kwargs_source, kwargs_lens_light, kwargs_else, no_noise)
        return image

    def simulate(self, kwargs_options, kwargs_data, kwargs_psf, kwargs_lens, kwargs_source, kwargs_lens_light, kwargs_else, no_noise=False, source_add=True, lens_light_add=True, point_source_add=True):
        """
        simulate image
        :param kwargs_options:
        :param kwargs_data:
        :param kwargs_psf:
        :param kwargs_lens:
        :param kwargs_source:
        :param kwargs_lens_light:
        :param kwargs_else:
        :param no_noise:
        :return:
        """
        makeImage = MakeImage(kwargs_options=kwargs_options, kwargs_data=kwargs_data, kwargs_psf=kwargs_psf)
        image, error_map = makeImage.image_with_params(kwargs_lens, kwargs_source, kwargs_lens_light, kwargs_else, source_add=source_add, lens_light_add=lens_light_add, point_source_add=point_source_add)
        image = makeImage.Data.array2image(image)
        # add noise
        if no_noise:
            return image
        else:
            poisson = util.add_poisson(image, exp_time=util.array2image(kwargs_data['exposure_map']))
            bkg = util.add_background(image, sigma_bkd=kwargs_data['sigma_background'])
            return image + bkg + poisson

    def fermat_potential(self, kwargs_options, kwargs_lens, kwargs_else):
        """
        computes the Fermat potential
        :param kwargs_options:
        :param kwargs_lens:
        :param kwargs_else:
        :param no_noise:
        :return: array of Fermat potential for all image positions (in ordering of kwargs_else['ra_pos'])
        """
        lensModel = LensModel(kwargs_options)
        fermat_pot = lensModel.fermat_potential(kwargs_lens, kwargs_else)
        return fermat_pot