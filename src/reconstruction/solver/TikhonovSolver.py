#!/usr/bin/python

## \file TikhonovSolver.py
#  \brief Implementation to get an approximate solution of the inverse problem 
#  \f$ y_k = A_k x \f$ for each slice \f$ y_k,\,k=1,\dots,K \f$
#  by using Tikhonov-regularization
#
#  \author Michael Ebner (michael.ebner.14@ucl.ac.uk)
#  \date July 2016

## Import libraries
import os                       # used to execute terminal commands in python
import sys
import itk
import SimpleITK as sitk
import numpy as np
from scipy.sparse.linalg import LinearOperator
from scipy.sparse.linalg import lsqr
from scipy.optimize import lsq_linear
from scipy.optimize import nnls

## Add directories to import modules
dir_src_root = "../src/"
sys.path.append( dir_src_root + "base/" )
sys.path.append( dir_src_root + "reconstruction/" )
sys.path.append( dir_src_root + "reconstruction/solver/" )

## Import modules
import SimpleITKHelper as sitkh
import DifferentialOperations as diffop
from Solver import Solver

## Pixel type of used 3D ITK image
PIXEL_TYPE = itk.D

## ITK image type 
IMAGE_TYPE = itk.Image[PIXEL_TYPE, 3]


## This class implements the framework to iteratively solve 
#  \f$ \vec{y}_k = A_k \vec{x} \f$ for every slice \f$ \vec{y}_k,\,k=1,\dots,K \f$
#  via Tikhonov-regularization via an augmented least-square approach
#  where \f$A_k=D_k B_k W_k\in\mathbb{R}^{N_k}\f$ denotes the combined warping, blurring and downsampling 
#  operation, \f$ M_k \f$ the masking operator and \f$G\f$ represents either 
#  the identity matrix \f$I\f$ (zeroth-order Tikhonov) or 
#  the (flattened, stacked vector) gradient 
#  \f$ \nabla  = \begin{pmatrix} D_x \\ D_y \\ D_z \end{pmatrix} \f$ 
#  (first-order Tikhonov).
#  The minimization problem reads
#  \f[
#       \text{arg min}_{\vec{x}} \Big( \sum_{k=1}^K \frac{1}{2} \Vert M_k (\vec{y}_k - A_k \vec{x} )\Vert_{\ell^2}^2 
#                       + \frac{\alpha}{2}\,\Vert G\vec{x} \Vert_{\ell^2}^2 \Big)
#       = 
#       \text{arg min}_{\vec{x}} \Bigg( \Bigg\Vert 
#           \begin{pmatrix} M_1 A_1 \\ M_2 A_2 \\ \vdots \\ M_K A_K \\ \sqrt{\alpha} G \end{pmatrix} \vec{x}
#           - \begin{pmatrix} M_1 \vec{y}_1 \\ M_2 \vec{y}_2 \\ \vdots \\ M_K \vec{y}_K \\ \vec{0} \end{pmatrix}
#       \Bigg\Vert_{\ell^2}^2 \Bigg)
#  \f] 
#  By defining the shorthand 
#  \f[ 
#   MA := \begin{pmatrix} M_1 A_1 \\ M_2 A_2 \\ \vdots \\ M_K A_K \end{pmatrix}\in\mathbb{R}^{\sum_k N_k} \quad\text{and}\quad
#   M\vec{y} := \begin{pmatrix} M_1 \vec{y}_1 \\ M_2 \vec{y}_2 \\ \vdots \\ M_K \vec{y}_K \end{pmatrix}\in\mathbb{R}^{\sum_k N_k} 
#  \f]
#  the problem can be compactly written as
#  \f[
#       \text{arg min}_{\vec{x}} \Bigg( \Bigg\Vert 
#           \begin{pmatrix} MA \\ \sqrt{\alpha} G \end{pmatrix} \vec{x}
#           - \begin{pmatrix} M\vec{y} \\ \vec{0} \end{pmatrix}
#       \Bigg\Vert_{\ell^2}^2 \Bigg)
#  \f]
#  with \f$ G\in\mathbb{R}^N \f$ in case of \f$G=I\f$ or 
#  \f$G\in\mathbb{R}^{3N}\f$ in case of \f$G\f$ representing the gradient.
#  \see \p itkAdjointOrientedGaussianInterpolateImageFilter of \p ITK
#  \see \p itOrientedGaussianInterpolateImageFunction of \p ITK
class TikhonovSolver(Solver):

    ## Constructor
    #  \param[in] stacks list of Stack objects containing all stacks used for the reconstruction
    #  \param[in] HR_volume Stack object containing the current estimate of the HR volume (used as initial value + space definition)
    #  \param[in] alpha_cut Cut-off distance for Gaussian blurring filter
    def __init__(self, stacks, HR_volume, alpha_cut=3, alpha=0.02, iter_max=10, reg_type="TK1"):

        Solver.__init__(self, stacks, HR_volume, alpha_cut)

        ## Compute total amount of pixels for all slices
        self._N_total_slice_voxels = 0
        for i in range(0, self._N_stacks):
            N_stack_voxels = np.array(self._stacks[i].sitk.GetSize()).prod()
            self._N_total_slice_voxels += N_stack_voxels

        ## Compute total amount of voxels of x:
        self._N_voxels_HR_volume = np.array(self._HR_volume.sitk.GetSize()).prod()

        ## Define differential operators
        spacing = self._HR_volume.sitk.GetSpacing()[0]
        self._differential_operations = diffop.DifferentialOperations(step_size=spacing)                  
        
        ## Settings for optimizer
        self._alpha = alpha
        self._iter_max = iter_max
        self._reg_type = reg_type

        self._A = {
            "TK0"   : self._A_TK0,
            "TK1"   : self._A_TK1
        }

        self._A_adj = {
            "TK0"   : self._A_adj_TK0,
            "TK1"   : self._A_adj_TK1
        }

    ## Set type of regularization. It can be either 'TK0' or 'TK1'
    #  \param[in] reg_type Either 'TK0' or 'TK1', string
    def set_regularization_type(self, reg_type):
        if reg_type not in ["TK0", "TK1"]:
            raise ValueError("Error: regularization type can only be either 'TK0' or 'TK1'")

        self._reg_type = reg_type


    ## Get chosen type of regularization.
    #  \return regularization type as string
    def get_regularization_type(self):
        return self._reg_type


    ## Set regularization parameter
    #  \param[in] alpha regularization parameter, scalar
    def set_alpha(self, alpha):
        self._alpha = alpha


    ## Get value of chosen regularization parameter
    #  \return regularization parameter, scalar
    def get_alpha(self):
        return self._alpha


    ## Set maximum number of iterations for minimizer
    #  \param[in] iter_max number of maximum iterations, scalar
    def set_iter_max(self, iter_max):
        self._iter_max = iter_max


    ## Get chosen value of maximum number of iterations for minimizer
    #  \return maximum number of iterations set for minimizer, scalar
    def get_iter_max(self):
        return self._iter_max

    ## Run the reconstruction algorithm. Result can be fetched by \p get_HR_volume
    def run_reconstruction(self):

        ## Compute number of voxels to be stored for augmented linear system
        if self._reg_type in ["TK0"]:
            print("Chosen regularization type: zero-order Tikhonov")
            print("Regularization parameter = " + str(self._alpha))
            print("Maximum number of iterations = " + str(self._iter_max))
            # print("Tolerance = %.0e" %(self._tolerance))

            ## G = Identity:
            N_voxels = self._N_total_slice_voxels + self._N_voxels_HR_volume

        else:
            print("Chosen regularization type: first-order Tikhonov")
            print("Regularization parameter = " + str(self._alpha))
            print("Maximum number of iterations = " + str(self._iter_max))
            # print("Tolerance = %.0e" %(self._tolerance))

            ## G = [Dx, Dy, Dz]^T, i.e. gradient computation:
            N_voxels = self._N_total_slice_voxels + 3*self._N_voxels_HR_volume

        ## Construct right-hand side b
        b = self._get_b(N_voxels)

        ## Construct (sparse) linear operator A
        A_fw = lambda x: self._A[self._reg_type](x, N_voxels, self._alpha)
        A_bw = lambda x: self._A_adj[self._reg_type](x, self._alpha)
        A = LinearOperator((N_voxels, self._N_voxels_HR_volume), matvec=A_fw, rmatvec=A_bw)

        # HR_nda = sitk.GetArrayFromImage(self._HR_volume.sitk)

        # res = lsq_linear(A, b, bounds=(0, np.inf), max_iter=self._iter_max, lsq_solver=None, lsmr_tol='auto', verbose=2)
        # res = lsq_linear(A, b, max_iter=self._iter_max, lsq_solver=None, lsmr_tol='auto', verbose=2)
        # res = nnls(A,b) #does not work with sparse linear operator

        res = lsqr(A, b, iter_lim=self._iter_max, show=True) #Works neatly (but does not allow bounds)

        ## Extract estimated solution as numpy array
        HR_nda_vec = res[0]

        ## After reconstruction: Update member attribute
        self._HR_volume.itk = self.get_itk_image_from_array_vec( HR_nda_vec, self._HR_volume.itk )
        self._HR_volume.sitk = sitkh.convert_itk_to_sitk_image( self._HR_volume.itk )


    ## Compute
    #  \f$ b := \begin{pmatrix} M_1 \vec{y}_1 \\ M_2 \vec{y}_2 \\ \vdots \\ M_K \vec{y}_K \\ \vec{0}\end{pmatrix} \f$ 
    #  \param[in] N_voxels number of voxels (only two possibilities depending on G), integer
    #  \return vector b as 1D array
    def _get_b(self, N_voxels):

        ## Allocate memory
        b = np.zeros(N_voxels)

        ## Define index for first voxel of first slice within array
        i_min = 0

        for i in range(0, self._N_stacks):
            stack = self._stacks[i]
            slices = stack.get_slices()

            ## Get number of voxels of each slice in current stack
            N_slice_voxels = np.array(slices[0].sitk.GetSize()).prod()

            for j in range(0, stack.get_number_of_slices()):

                ## Define index for last voxel to specify current slice (exlusive)
                i_max = i_min + N_slice_voxels

                ## Get current slice
                slice_k = slices[j]

                ## Apply M_k y_k
                slice_itk = self.Mk(slice_k.itk, slice_k)
                slice_nda_vec = self._itk2np.GetArrayFromImage(slice_itk).flatten()

                ## Fill respective elements
                b[i_min:i_max] = slice_nda_vec

                ## Define index for first voxel to specify subsequent slice (inclusive)
                i_min = i_max

        return b


    """
    TK0-Solver
    """ 
    ## Evaluate augmented linear operator for TK0-regularization, i.e.
    #  \f$
    #       \begin{pmatrix} MA \\ \sqrt{\alpha} G \end{pmatrix} \vec{x}
    #     = \begin{pmatrix} M_1 A_1 \\ M_2 A_2 \\ \vdots \\ M_K A_K \\ \sqrt{\alpha} I \end{pmatrix} \vec{x}
    #  \f$
    #  for \f$ G = I\f$ identity matrix
    #  \param[in] HR_nda_vec HR data as 1D array
    #  \param[in] N_voxels number of voxels (only two possibilities depending on G), integer
    #  \param[in] alpha regularization parameter, scalar
    #  \return evaluated augmented linear operator as 1D array
    def _A_TK0(self, HR_nda_vec, N_voxels, alpha):

        ## Allocate memory
        A_x = np.zeros(N_voxels)

        ## Compute MA x
        A_x[0:-self._N_voxels_HR_volume] = self.MA(HR_nda_vec)

        ## Compute sqrt(alpha)*x
        A_x[-self._N_voxels_HR_volume:] = np.sqrt(alpha)*HR_nda_vec

        return A_x

    ## Evaluate the adjoint augmented linear operator for TK0-regularization, i.e.
    #  \f$
    #       \begin{bmatrix} A^* M && \sqrt{\alpha} G^* \end{bmatrix} \vec{y}
    #     = \begin{bmatrix} A_1^* M_1 && A_2^* M_2 && \cdots && A_K^* M_K && \sqrt{\alpha} I \end{bmatrix} \vec{y}
    #  \f$
    #  for \f$ G = I\f$ identity matrix and \f$\vec{y}\in\mathbb{R}^{\sum_k N_k + N}\f$ 
    #  representing a vector of stacked slices
    #  \param[in] stacked_slices_nda_vec stacked slice data as 1D array
    #  \param[in] alpha regularization parameter, scalar
    #  \return evaluated augmented adjoint linear operator as 1D array
    def _A_adj_TK0(self, stacked_slices_nda_vec, alpha):

        ## Compute A'M y[upper] 
        A_adj_y = self.A_adj_M(stacked_slices_nda_vec)

        ## Add sqrt(alpha)*y[lower]
        A_adj_y = A_adj_y + stacked_slices_nda_vec[-self._N_voxels_HR_volume:]*np.sqrt(alpha)

        return A_adj_y


    """
    TK1-Solver
    """
    ## Evaluate augmented linear operator for TK1-regularization, i.e.
    #  \f$
    #       \begin{pmatrix} MA \\ \sqrt{\alpha} G \end{pmatrix} \vec{x}
    #     = \begin{pmatrix} M_1 A_1 \\ M_2 A_2 \\ \vdots \\ M_K A_K \\ \sqrt{\alpha} D \end{pmatrix} \vec{x}
    #  \f$
    #  for \f$ G = D\f$ representing the gradient.
    #  \param[in] HR_nda_vec HR data as 1D array
    #  \param[in] N_voxels number of voxels (only two possibilities depending on G), integer
    #  \param[in] alpha regularization parameter, scalar
    #  \return evaluated augmented linear operator as 1D array
    def _A_TK1(self, HR_nda_vec, N_voxels, alpha):

        ## Allocate memory
        A_x = np.zeros(N_voxels)

        ## Compute MAx 
        A_x[0:-3*self._N_voxels_HR_volume] = self.MA(HR_nda_vec)

        ## Compute sqrt(alpha)*Dx
        A_x[-3*self._N_voxels_HR_volume:] = np.sqrt(alpha)*self.D(HR_nda_vec)

        return A_x


    ## Evaluate the adjoint augmented linear operator for TK1-regularization, i.e.
    #  \f$
    #       \begin{bmatrix} A^* M && \sqrt{\alpha} G^* \end{bmatrix} \vec{y}
    #     = \begin{bmatrix} A_1^* M_1 && A_2^* M_2 && \cdots && A_K^* M_K && \sqrt{\alpha} D^* \end{bmatrix} \vec{y}
    #  \f$
    #  for \f$ G = D\f$ representing the gradient and \f$\vec{y}\in\mathbb{R}^{\sum_k N_k + 3N}\f$ 
    #  representing a vector of stacked slices
    #  \param[in] stacked_slices_nda_vec stacked slice data as 1D array
    #  \param[in] alpha regularization parameter, scalar
    #  \return evaluated augmented adjoint linear operator 
    def _A_adj_TK1(self, stacked_slices_nda_vec, alpha):

        ## Compute A'M y[upper]
        A_adj_y = self.A_adj_M(stacked_slices_nda_vec)

        ## Add D' y[lower]
        A_adj_y = A_adj_y + self.D_adj(stacked_slices_nda_vec).flatten()*np.sqrt(alpha)

        return A_adj_y

                
            