# \file RegistrationSimpleITK.py
#  \brief Registration class based on SimpleITK
#
#  \author Michael Ebner (michael.ebner.14@ucl.ac.uk)
#  \date May 2016

# Import libraries
import os
import sys
import itk
import SimpleITK as sitk
import numpy as np

# Used to parse variable arguments to SimpleITK object, see
# http://stackoverflow.com/questions/20263839/python-convert-a-string-to-arguments-list:
from ast import literal_eval

# Import modules from src-folder
import pythonhelper.SimpleITKHelper as sitkh
import pythonhelper.PythonHelper as ph
import base.Stack as st
import base.PSF as psf


class RegistrationSimpleITK:

    def __init__(self,
                 fixed=None,
                 moving=None,
                 use_fixed_mask=False,
                 use_moving_mask=False,
                 registration_type="Rigid",
                 interpolator="Linear",
                 metric="Correlation",
                 metric_params=None,
                 optimizer="ConjugateGradientLineSearch",
                 optimizer_params="{'learningRate': 1, 'numberOfIterations': 100}",
                 # optimizer="RegularStepGradientDescent",
                 # optimizer_params="{'learningRate': 1, 'minStep': 1e-6,
                 # 'numberOfIterations': 200, 'gradientMagnitudeTolerance':
                 # 1e-6}",
                 scales_estimator="PhysicalShift",
                 initializer_type=None,
                 use_oriented_psf=False,
                 use_multiresolution_framework=False,
                 shrink_factors=[4, 2, 1],
                 smoothing_sigmas=[2, 1, 0],
                 use_verbose=False,
                 ):

        self._fixed = fixed
        self._moving = moving

        self._use_fixed_mask = use_fixed_mask
        self._use_moving_mask = use_moving_mask

        self._registration_type = registration_type

        self._interpolator = interpolator
        self._metric = metric
        self._metric_params = metric_params

        self._optimizer = optimizer
        self._optimizer_params = optimizer_params

        self._scales_estimator = scales_estimator

        self._initializer_type = initializer_type

        self._use_oriented_psf = use_oriented_psf

        self._use_multiresolution_framework = use_multiresolution_framework
        self._shrink_factors = shrink_factors
        self._smoothing_sigmas = smoothing_sigmas

        self._use_verbose = use_verbose

    # Set fixed/reference/target image
    #  \param[in] fixed fixed/reference/target image as Stack object
    def set_fixed(self, fixed):
        self._fixed = fixed

    # Set moving/floating/source image
    #  \param[in] moving moving/floating/source image as Stack object
    def set_moving(self, moving):
        self._moving = moving

    # Specify whether mask shall be used for fixed image
    #  \param[in] flag boolean
    def use_fixed_mask(self, flag):
        self._use_fixed_mask = flag

    # Specify whether mask shall be used for moving image
    #  \param[in] flag boolean
    def use_moving_mask(self, flag):
        self._use_moving_mask = flag

    # Use multiresolution framework
    #  \param[in] flag boolean
    def use_multiresolution_framework(self, flag):
        self._use_multiresolution_framework = flag

    # Decide whether oriented PSF shall be applied, i.e. blur moving image
    #  with (axis aligned) Gaussian kernel given by the relative position of
    #  the coordinate systems of fixed and moving
    #  \param[in] flag boolean
    def use_oriented_psf(self, flag):
        self._use_oriented_psf = flag

    # Set type of registration used
    #  \param[in] registration_type
    def set_registration_type(self, registration_type):
        if registration_type not in ["Rigid", "Similarity", "Affine"]:
            raise ValueError(
                "Error: Registration type can only be 'Rigid', 'Similarity' or 'Affine'")

        self._registration_type = registration_type

    # Get type of registration
    def get_registration_type(self):
        return registration_type

    # Set type of centered transform initializer
    #  \param[in] initializer_type
    def set_initializer_type(self, initializer_type):
        if initializer_type not in [None, "MOMENTS", "GEOMETRY"]:
            raise ValueError(
                "Error: centered transform initializer type can only be 'None', MOMENTS' or 'GEOMETRY'")
        else:
            self._initializer_type = initializer_type

    # Get type of centered transform initializer
    def get_centered_transform_initializer(self):
        return self._initializer_type

    # Get affine transform in (Simple)ITK format after having run reg_aladin
    #  \return affine transform as SimpleITK object
    def get_registration_transform_sitk(self):
        return self._transform_sitk

    # Get registered image
    #  \return registered image as Stack object
    def get_corrected_stack(self):
        corrected_stack = st.Stack.from_stack(self._fixed)
        corrected_stack.update_motion_correction(self._transform_sitk)
        return corrected_stack

    # Set interpolator
    #  \param[in] interpolator_type
    def set_interpolator(self, interpolator_type):

        if interpolator_type not in ["Linear", "NearestNeighbor", "BSpline"]:
            raise ValueError(
                "Error: Interpolator can only be either 'Linear', 'NearestNeighbor' or 'BSpline'")

        self._interpolator = interpolator_type

    # Get interpolator
    #  \return interpolator as string
    def get_interpolator(self):
        return self._interpolator

    # Set metric for registration method
    #  \param[in] metric as string
    #  \param[in] params as string in form of dictionary
    #  \example metric="Correlation"
    #  \example metric="MattesMutualInformation", params="{'numberOfHistogramBins': 100}"
    #  \example metric="ANTSNeighborhoodCorrelation", params="{'radius': 10}"
    #  \example metric="JointHistogramMutualInformation", params="{'numberOfHistogramBins': 10, 'varianceForJointPDFSmoothing': 1}"
    #  \example metric="Demons", params="{'intensityDifferenceThreshold': 1e-3}"
    def set_metric(self, metric, params=None):

        if metric not in [
                # Use negative means squares image metric
                "MeanSquares",

                # Use negative normalized cross correlation image metric
                "Correlation",

                # Use normalized cross correlation using a small neighborhood
                # for each voxel between two images, with speed optimizations
                # for dense registration
                "ANTSNeighborhoodCorrelation",

                # Use mutual information between two images
                "JointHistogramMutualInformation",

                # Use the mutual information between two images to be
                # registered using the method of Mattes2001
                "MattesMutualInformation",

            # Use demons image metric
            "Demons"
        ]:
            raise ValueError("Error: Metric is not known")

        self._metric = metric
        self._metric_params = params

        # Set default value in case params is not given
        if metric in ["ANTSNeighborhoodCorrelation"] and params is None:
            self._metric_params = "{'radius': 10}"

        # elif metric in ["MattesMutualInformation"] and params is None:
        #     self._metric_params = "{'numberOfHistogramBins': 100}"

    # Set optimizer used by registration method
    #  \param[in] optimizer as string
    #  \param[in] params as string in form of dictionary
    def set_optimizer(self, optimizer, params=None):
        if optimizer not in [
                # Set optimizer to Nelder-Mead downhill simplex algorithm
                "Amoeba",

                # Regular Step Gradient descent optimizer
                "RegularStepGradientDescent",

                # Gradient descent optimizer with a golden section line search
                "GradientDescentLineSearch",

                # Conjugate gradient descent optimizer with a golden section
                # line search for nonlinear optimization
                "ConjugateGradientLineSearch",

            # Limited memory Broyden Fletcher Goldfarb Shannon minimization
            # with simple bounds
            "LBFGSB"
        ]:
            raise ValueError("Error: Optimizer is not known")

        self._optimizer = optimizer
        self._optimizer_params = params

        # Set default values in case params is not given
        if optimizer in ["Amoeba"] and params is None:
            self._optimizer_params = "{'simplexDelta': 0.1, 'numberOfIterations': 100, 'parametersConvergenceTolerance': 1e-8, 'functionConvergenceTolerance': 1e-4, 'withRestarts':False}"

        elif optimizer in ["RegularStepGradientDescent"] and params is None:
            self._optimizer_params = "{'learningRate': 1, 'minStep': 1e-6, 'numberOfIterations': 400, 'gradientMagnitudeTolerance': 1e-6}"

        elif optimizer in ["GradientDescentLineSearch"] and params is None:
            self._optimizer_params = "{'learningRate': 1, 'numberOfIterations': 100, 'convergenceMinimumValue': 1e-6, 'convergenceWindowSize':10}"

        elif optimizer in ["ConjugateGradientLineSearch"] and params is None:
            self._optimizer_params = "{'learningRate': 1, 'numberOfIterations': 100, 'convergenceMinimumValue': 1e-8, 'convergenceWindowSize': 10}"

        elif optimizer in ["LBFGSB"] and params is None:
            self._optimizer_params = "{'gradientConvergenceTolerance': 1e-5, 'maximumNumberOfIterations': 100, 'maximumNumberOfCorrections': 5, 'maximumNumberOfFunctionEvaluations': 200, 'costFunctionConvergenceFactor': 1e+7}"

    # Set optimizer scales
    #  \param[in] scales
    def set_scales_estimator(self, scales_estimator):
        if scales_estimator not in ["IndexShift", "PhysicalShift", "Jacobian"]:
            raise ValueError("Error: Optimizer scales_estimator not known")

        self._scales_estimator = scales_estimator

    ##
    #       Sets the verbose to define whether or not output is produced
    # \date       2016-09-20 18:49:19+0100
    #
    # \param      self     The object
    # \param      verbose  The verbose
    #
    def use_verbose(self, flag):
        self._use_verbose = flag

    ##
    #       Gets the verbose.
    # \date       2016-09-20 18:49:54+0100
    #
    # \param      self  The object
    #
    # \return     The verbose.
    #
    def get_verbose(self):
        return self._use_verbose

    # Run registration
    def run_registration(self, id=None):
        self._run_registration(self._fixed, self._moving)

    def _run_registration(self, fixed, moving):

        dim = fixed.sitk.GetDimension()

        # Blur moving image with oriented Gaussian prior to the registration
        if self._use_oriented_psf:

            # Get oriented Gaussian covariance matrix
            cov_HR_coord = psf.PSF().get_gaussian_PSF_covariance_matrix_HR_volume_coordinates(fixed, moving)

            # Create recursive YVV Gaussianfilter
            image_type = itk.Image[itk.D, dim]
            gaussian_yvv = itk.SmoothingRecursiveYvvGaussianImageFilter[
                image_type, image_type].New()

            # Feed Gaussian filter with axis aligned covariance matrix
            sigma_axis_aligned = np.sqrt(np.diagonal(cov_HR_coord))
            print("Oriented PSF blurring with (axis aligned) sigma = " +
                  str(sigma_axis_aligned))
            print("\t(Based on computed covariance matrix = ")
            for i in range(0, 3):
                print("\t\t" + str(cov_HR_coord[i, :]))
            print("\twith square root of diagonal " +
                  str(np.diagonal(cov_HR_coord)) + ")")

            gaussian_yvv.SetInput(moving.itk)
            gaussian_yvv.SetSigmaArray(sigma_axis_aligned)
            gaussian_yvv.Update()
            moving_itk = gaussian_yvv.GetOutput()
            moving_itk.DisconnectPipeline()
            moving_sitk = sitkh.get_sitk_from_itk_image(moving_itk)

        else:
            moving_sitk = moving.sitk

        # Instantiate interface method to the modular ITKv4 registration
        # framework
        registration_method = sitk.ImageRegistrationMethod()

        # Set the initial transform and parameters to optimize
        if self._registration_type in ["Rigid"]:
            initial_transform = eval("sitk.Euler" + str(dim) + "DTransform()")

        elif self._registration_type in ["Similarity"]:
            initial_transform = eval(
                "sitk.Similarity" + str(dim) + "DTransform()")

        elif self._registration_type in ["Affine"]:
            initial_transform = sitk.AffineTransform(dim)

        if self._initializer_type is not None:
            initial_transform = sitk.CenteredTransformInitializer(fixed.sitk, moving.sitk, initial_transform, eval(
                "sitk.CenteredTransformInitializerFilter." + self._initializer_type))
        registration_method.SetInitialTransform(
            initial_transform, inPlace=True)

        # Set an image masks in order to restrict the sampled points for the
        # metric
        if self._use_moving_mask:
            registration_method.SetMetricMovingMask(moving.sitk_mask)

        if self._use_fixed_mask:
            registration_method.SetMetricFixedMask(fixed.sitk_mask)

        # Set percentage of pixels sampled for metric evaluation
        # registration_method.SetMetricSamplingStrategy(registration_method.NONE)

        # Set interpolator
        eval("registration_method.SetInterpolator(sitk.sitk" +
             self._interpolator + ")")

        # Set similarity metric
        if self._metric_params is None:
            eval("registration_method.SetMetricAs" + self._metric)()
        else:
            eval("registration_method.SetMetricAs" +
                 self._metric)(**literal_eval(self._metric_params))

        # Set Optimizer
        # if self._optimizer_params is None:
        #     eval("registration_method.SetOptimizerAs" + self._optimizer)()
        # else:
        eval("registration_method.SetOptimizerAs" +
             self._optimizer)(**literal_eval(self._optimizer_params))

        # Set the optimizer to sample the metric at regular steps
        # registration_method.SetOptimizerAsExhaustive(numberOfSteps=50,
        # stepLength=1.0)

        # Estimating scales of transform parameters a step sizes, from the
        # maximum voxel shift in physical space caused by a parameter change
        eval("registration_method.SetOptimizerScalesFrom" +
             self._scales_estimator)()

        # Optional multi-resolution framework
        if self._use_multiresolution_framework:
            # Set the shrink factors for each level where each level has the
            # same shrink factor for each dimension
            registration_method.SetShrinkFactorsPerLevel(
                shrinkFactors=self._shrink_factors)

            # Set the sigmas of Gaussian used for smoothing at each level
            registration_method.SetSmoothingSigmasPerLevel(
                smoothingSigmas=self._smoothing_sigmas)

            # Enable the smoothing sigmas for each level in physical units
            # (default) or in terms of voxels (then *UnitsOff instead)
            registration_method.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()

        # Connect all of the observers so that we can perform plotting during registration
        # registration_method.AddCommand(sitk.sitkStartEvent, start_plot)
        # registration_method.AddCommand(sitk.sitkEndEvent, end_plot)
        # registration_method.AddCommand(sitk.sitkMultiResolutionIterationEvent, update_multires_iterations)
        # registration_method.AddCommand(sitk.sitkIterationEvent, lambda:
        # plot_values(registration_method))

        # print('  Final metric value: {0}'.format(registration_method.GetMetricValue()))
        # print('  Optimizer\'s stopping condition, {0}'.format(registration_method.GetOptimizerStopConditionDescription()))
        # print("\n")

        if self._use_verbose:
            ph.print_info("Registration: SimpleITK")
            ph.print_info("Transform Model: %s"
                          % (self._registration_type))
            ph.print_info("Interpolator: %s"
                          % (self._interpolator))
            ph.print_info("Metric: %s" % (self._metric))
            ph.print_info("CenteredTransformInitializer: %s"
                          % (self._initializer_type))
            ph.print_info("Optimizer: %s"
                          % (self._optimizer))
            ph.print_info("Use Multiresolution Framework: %s"
                          % (self._use_multiresolution_framework) +
                          " (" +
                          "shrink factors = " + str(self._shrink_factors) +
                          ", " +
                          "smoothing sigmas = " + str(self._smoothing_sigmas) +
                          ")"
                          )
            ph.print_info("Use Fixed Mask: %s"
                          % (self._use_fixed_mask))
            ph.print_info("Use Moving Mask: %s"
                          % (self._use_moving_mask))

        # Execute 3D registration
        try:
            registration_transform_sitk = registration_method.Execute(
                fixed.sitk, moving_sitk)
        except RuntimeError as err:
            print(err.message)
            # Debug:
            # sitkh.show_sitk_image(
            # [fixed.sitk, moving_sitk], segmentation=fixed.sitk_mask)

            print("WARNING: SetMetricAsCorrelation")
            registration_method.SetMetricAsCorrelation()
            registration_transform_sitk = registration_method.Execute(
                fixed.sitk, moving_sitk)

        if self._registration_type in ["Rigid"]:
            registration_transform_sitk = eval(
                "sitk.Euler" + str(dim) + "DTransform(registration_transform_sitk)")
        elif self._registration_type in ["Similarity"]:
            registration_transform_sitk = eval(
                "sitk.Similarity" + str(dim) + "DTransform(registration_transform_sitk)")
        elif self._registration_type in ["Affine"]:
            registration_transform_sitk = sitk.AffineTransform(
                registration_transform_sitk)

        if self._use_verbose:
            ph.print_info("SimpleITK Image Registration Method:")
            ph.print_info('\tFinal metric value: {0}'.format(
                registration_method.GetMetricValue()))
            ph.print_info('\tOptimizer\'s stopping condition, {0}'.format(
                registration_method.GetOptimizerStopConditionDescription()))

            sitkh.print_sitk_transform(registration_transform_sitk)

        self._transform_sitk = registration_transform_sitk
