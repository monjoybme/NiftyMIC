## \file Registration.py
#  \brief  
# 
#  \author Michael Ebner
#  \date June 2015


## Import libraries
import nibabel as nib           # nifti files
import numpy as np
import numpy.linalg as npl
import os                       # used to execute terminal commands in python
import sys


## Import other py-files within src-folder
from FetalImage import *


## Global variables to store computed results
global dir_out
global clear_dir_out

dir_out = "../results/tmp/"
clear_dir_out = 0

## \brief some description
class Registration:

    def __init__(self, fetal_stacks, target_stack_id):

        if clear_dir_out:
            cmd = "rm " + dir_out + "*"
            os.system(cmd)


        self._fetal_stacks = fetal_stacks
        self._target_stack = fetal_stacks[target_stack_id]
        self._corrected_stacks = [None]*len(fetal_stacks)

        try:
            ## Initialize first HR volume as uniformly resampled target stack
            filename = "HR_volume_" + self._target_stack.get_filename()
            if os.path.isfile(dir_out + filename + ".nii.gz"):
                # raise ValueError("HR volume already exists!")
                print ("HR volume was read from directory")
            else:
                self.resample_to_isotropic_grid(fetal_stacks[target_stack_id], filename)
            self._HR_volume = FetalImage(dir_out, filename)


            ## Initialize corrected stacks with raw fetal stacks
            for i in range(0,len(fetal_stacks)):
                filename = self._fetal_stacks[i].get_filename()

                ## Copy files in case they do not exist
                if  os.path.isfile(dir_out + filename + ".nii.gz"):
                    # raise ValueError("Corrected stacks already exist!")
                    print("Corrected stack %d was read from directory" % i)
                else:
                    cmd = "cp " + self._fetal_stacks[i].get_dir() \
                                + self._fetal_stacks[i].get_filename() + ".nii.gz " \
                                + dir_out + filename + ".nii.gz"
                    # print cmd
                    os.system(cmd)

                self._corrected_stacks[i] = FetalImage(dir_out, filename)


        except ValueError as err:
            print(err.args)



    def get_fetal_stacks(self):
        return self._fetal_stacks


    def get_target_stack(self):
        return self._target_stack


    def get_HR_volume(self):
        return self._HR_volume


    def get_corrected_stacks(self):
        return self._corrected_stacks


    ## Register stacks rigidly to current HR volume
    def register_images(self):

        ## Create folder if not already existing
        os.system("mkdir -p " + dir_out)

        ## Amount of used stacks for volumetric reconstruction
        N_stacks = len(self._fetal_stacks)
        # print N_stacks

        ## Fetch data of current HR volume
        dir_ref = self._HR_volume.get_dir()
        ref_filename = self._HR_volume.get_filename()

        ## Compute rigid registration of each stack by using NiftyReg
        for i in range(0, N_stacks):

            ## Fetch data of motion corrupted slices
            dir_flo = self._corrected_stacks[i].get_dir()
            flo_filename = self._corrected_stacks[i].get_filename()

            ## Define filenames of resulting rigidly registered stacks
            res_filename = flo_filename
            aff_filename = flo_filename

            # options = "-voff -platf Cuda=1 "
            options = "-voff "

            ## NiftyReg: Global affine registration of reference image:
            #  \param[in] -ref reference image
            #  \param[in] -flo floating image
            #  \param[out] -res affine registration of floating image
            #  \param[out] -aff affine transformation matrix
            cmd = "reg_aladin " + options + \
                "-ref " + dir_ref + ref_filename + ".nii.gz " + \
                "-flo " + dir_flo + flo_filename + ".nii.gz " + \
                "-res " + dir_out + res_filename + ".nii.gz " + \
                "-aff " + dir_out + aff_filename + ".txt"
            # print(cmd)

            print "Job %d/%d ... " % (i+1,N_stacks)
            os.system(cmd)
            print("............. done" % (i+1,N_stacks))

            ## Update results
            self._corrected_stacks[i] = FetalImage(dir_out, res_filename)

        return None


    ## Resample image to isotropic grid
    #  \param[in] img instance of FetalImage 
    #  \param[in] filename resampled image is saved as filename.nii.gz in dir_out
    #  \param[in] order interpolation order
    def resample_to_isotropic_grid(self, img, filename, order=0):
        
        ## fetch nifti-data for resampling
        header = img.get_header()
        shape = header.get_data_shape()
        pixdim =  header.get_zooms()      # voxel sizes in mm
        data = img.get_data()
        # sform = header.get_sform()
        # qform = header.get_qform()
        # print sform

        ## compute length of sampling in z-direction and new number of slices
        ## after rescaling their thickness to in-plane resolution
        length_through_plane = shape[2]*pixdim[2]
        number_of_slices_target_through_plane \
                = np.ceil(length_through_plane / float(pixdim[0])).astype(np.uint8)

        data_target = np.zeros(
            (shape[0], shape[1], number_of_slices_target_through_plane),
            dtype=np.int16
            )

        # print("shape = " + str(shape))
        # print("pixdim = " + str(pixdim) + " mm")
        # print("length_through_plane = " + str(length_through_plane) + " mm")
        # print img.get_data().shape
        # print img.affine
        # print(header.get_data_shape())
        # sform[2,0:2] = sform[2,0:2] * length_through_plane/pixdim[0]
        # print sform

        ## Nearest neighbour interpolation to uniform grid
        if (order == 0):
            i = 0
            for j in range(0,number_of_slices_target_through_plane):
                if (j > (i+1)*pixdim[2]/pixdim[0] and i < shape[2]-1):
                    i = i+1
                    # print("j="+str(j))
                    # print("i="+str(i))
                    # print("dist_fine = " + str((j+0.5)*pixdim[0]) )
                    # print("dist_coarse = " + str((i)*pixdim[2]) )
                    # print("\n")
                data_target[:,:,j] = data[:,:,i]


        ## Store data into nifti-object with appropriate header information
        img_target_nib = nib.Nifti1Image(data_target, img.get_affine())
        header_target = img_target_nib.get_header()
        header_target.set_zooms(pixdim[0]*np.ones(3))
        header_target.set_data_shape([shape[0],shape[1],number_of_slices_target_through_plane])
        # header_target.set_xyzt_units(2)
        # header_target.set_sform(sform,code=1)
        # header_target.set_qform(qform)

        # print(header_target.get_zooms())

        ## Save nifti-image to directory and create FetalImage instance
        img_target_nifti_filename = filename
        nib.save(img_target_nib, dir_out + img_target_nifti_filename + ".nii.gz")
        # img_target = FetalImage(dir_out, img_target_nifti_filename)

        ## NiftyReg: Resample to isotropic grid
        ## Comment: Resampling didn't work! Hence, manual resampling done!!
        #  \param[in] -inter interpolation order
        #  \param[in] -ref reference image
        #  \param[in] -flo floating image
        #  \param[in] -trans segmentation of floating image
        #  \param[out] -res propagated labels of flo image in ref-space
        # cmd = "reg_resample " + "-inter 0 " + \
        #     "-ref " + img_target_dummy.get_dir() + img_target_dummy.get_filename() + ".nii.gz " + \
        #     "-flo " + img.get_dir() + img.get_filename() + ".nii.gz " + \
        #     "-trans " + dir_out + "test-trafo.txt " \
        #     "-res " + dir_out + img_target_nifti_filename + ".nii.gz"
        # os.system(cmd)



        # nib.save(img_target, 'my_image.nii.gz')
        # print(img.zooms)

        return None


    def compute_HR_volume(self):
        N_stacks = len(self._fetal_stacks)

        data = np.zeros(self._HR_volume.get_data().shape)

        for i in range(0,N_stacks):
            # print self._corrected_stacks[i].data.shape
            data += self._corrected_stacks[i].get_data()

        data /= N_stacks

        self._HR_volume.set_data(data)

        return None
