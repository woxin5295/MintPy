#!/usr/bin/env python3
############################################################
# Program is part of PySAR                                 #
# Copyright(c) 2013-2018, Zhang Yunjun, Heresh Fattahi     #
# Author:  Zhang Yunjun, Heresh Fattahi                    #
############################################################


import os
import sys
import argparse
import h5py
import numpy as np
import matplotlib.pyplot as plt
from pysar.objects import ifgramStack, timeseries
from pysar.utils import (ptime,
                         readfile,
                         utils as ut,
                         network as pnet,
                         plot as pp)


###########################  Sub Function  #############################
BL_LIST = """
070106     0.0   0.03  0.0000000  0.00000000000 2155.2 /scratch/SLC/070106/
070709  2631.9   0.07  0.0000000  0.00000000000 2155.2 /scratch/SLC/070709/
070824  2787.3   0.07  0.0000000  0.00000000000 2155.2 /scratch/SLC/070824/
"""

DATE12_LIST = """
20070709_20100901
20070709_20101017
20070824_20071009
"""

EXAMPLE = """example:
  plot_network.py INPUTS/ifgramStack.h5
  plot_network.py INPUTS/ifgramStack.h5 -t pysarApp_template.txt --nodisplay  #Plot/save figure to files without display
  plot_network.py INPUTS/ifgramStack.h5 -t pysarApp_template.txt --nodrop     #Do not plot dropped ifgrams
  plot_network.py INPUTS/ifgramStack.h5 --save     #save ifgrams info to date12_list.txt file

  ##Plot network after select_network.py (without ifgramStack.h5 file)
  plot_network.py ifgram_list.txt  -b bl_list.txt
"""

TEMPLATE = """
pysar.network.maskFile  = auto  #[file name, no], auto for waterMask.h5 or no for all pixels
pysar.network.aoiYX     = auto  #[y0:y1,x0:x1 / no], auto for no, area of interest for coherence calculation
pysar.network.aoiLALO   = auto  #[lat0:lat1,lon0:lon1 / no], auto for no - use the whole area
"""


def create_parser():
    parser = argparse.ArgumentParser(description='Display Network of Interferograms',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     epilog=EXAMPLE)

    parser.add_argument('file',
                        help='file with network information, supporting:\n' +
                             'HDF5 file: ifgramStack.h5\n' +
                             'Text file: list of date12, generated by select_network.py or info.py, i.e.:'+DATE12_LIST)
    parser.add_argument('-b', '--bl', '--baseline', dest='bl_list_file', default='bl_list.txt',
                        help='baseline list file, generated using createBaselineList.pl, i.e.:'+BL_LIST)
    parser.add_argument('--nodrop', dest='disp_drop', action='store_false',
                        help='Do not display dropped interferograms')

    # Display coherence
    coh = parser.add_argument_group(
        'Display Coherence', 'Show coherence of each interferogram pair with color')
    coh.add_argument('-t', '--template', dest='template_file',
                     help='template file with options below:\n'+TEMPLATE)
    coh.add_argument('-m', dest='disp_min', type=float,
                     default=0.2, help='minimum coherence to display')
    coh.add_argument('-M', dest='disp_max', type=float,
                     default=1.0, help='maximum coherence to display')
    coh.add_argument('-c', '--colormap', dest='colormap', default='RdBu',
                     help='colormap for display, i.e. Blues, RdBu, jet, ...')
    coh.add_argument('--mask', dest='maskFile', default='waterMask.h5',
                     help='mask file used to calculate the coherence. Default: waterMask.h5 or None.')
    coh.add_argument('--threshold', dest='coh_thres', type=float,
                     help='coherence value of where to cut the colormap for display')

    # Figure  Setting
    fig = parser.add_argument_group('Figure', 'Figure settings for display')
    fig.add_argument('--fs', '--fontsize', type=int,
                     default=12, help='font size in points')
    fig.add_argument('--lw', '--linewidth', dest='linewidth',
                     type=int, default=2, help='line width in points')
    fig.add_argument('--mc', '--markercolor', dest='markercolor',
                     default='orange', help='marker color')
    fig.add_argument('--ms', '--markersize', dest='markersize',
                     type=int, default=16, help='marker size in points')
    fig.add_argument('--every-year', dest='every_year', type=int,
                     default=1, help='number of years per major tick on x-axis')

    fig.add_argument('--dpi', dest='fig_dpi', type=int, default=150,
                     help='DPI - dot per inch - for display/write')
    fig.add_argument('--figsize', dest='fig_size', type=float, nargs=2,
                     help='figure size in inches - width and length')
    fig.add_argument('--figext', dest='fig_ext',
                     default='.pdf', choices=['.emf', '.eps', '.pdf', '.png',
                                              '.ps', '.raw', '.rgba', '.svg',
                                              '.svgz', '.jpg'],
                     help='File extension for figure output file\n\n')
    fig.add_argument('--notitle', dest='disp_title', action='store_false',
                     help='Do not display figure title.')
    fig.add_argument('--number', dest='number', type=str,
                     help='number mark to be plot at the corner of figure.')
    fig.add_argument('--nosplit-cmap', dest='split_cmap', action='store_false',
                     help='do not split colormap for coherence color')


    fig.add_argument('--list', dest='save_list', action='store_true',
                     help='save pairs/date12 list into text file')
    fig.add_argument('--save', dest='save_fig',
                     action='store_true', help='save the figure')
    fig.add_argument('--nodisplay', dest='disp_fig',
                     action='store_false', help='save and do not display the figure')
    return parser


def cmd_line_parse(iargs=None):
    parser = create_parser()
    inps = parser.parse_args(args=iargs)

    if not inps.disp_fig:
        inps.save_fig = True

    if inps.template_file:
        inps = read_template2inps(inps.template_file, inps)

    if not os.path.isfile(inps.maskFile):
        inps.maskFile = None
    return inps


def read_template2inps(template_file, inps=None):
    """Read input template options into Namespace inps"""
    if not inps:
        inps = cmd_line_parse()
    inpsDict = vars(inps)
    print('read options from template file: '+os.path.basename(template_file))
    template = readfile.read_template(inps.template_file)
    template = ut.check_template_auto_value(template)

    # Coherence-based network modification
    prefix = 'pysar.network.'
    key = prefix+'maskFile'
    if key in template.keys():
        if template[key]:
            inps.maskFile = template[key]

    key = prefix+'minCoherence'
    if key in template.keys():
        if template[key]:
            inps.coh_thres = float(template[key])
    return inps


def read_network_info(inps):
    ext = os.path.splitext(inps.file)[1]

    # 1. Read dateList and pbaseList
    if ext in ['.h5', '.he5']:
        k = readfile.read_attribute(inps.file)['FILE_TYPE']
        print('reading temporal/spatial baselines from {} file: {}'.format(k, inps.file))
        if k == 'ifgramStack':
            inps.dateList = ifgramStack(inps.file).get_date_list(dropIfgram=False)
            inps.pbaseList = ifgramStack(inps.file).get_perp_baseline_timeseries(dropIfgram=False)
        elif k == 'timeseries':
            obj = timeseries(inps.file)
            obj.open(print_msg=False)
            inps.dateList = obj.dateList
            inps.pbaseList = obj.pbase
        else:
            raise ValueError('input file is not ifgramStack/timeseries, can not read temporal/spatial baseline info.')
    else:
        print('reading temporal/spatial baselines from list file: '+inps.bl_list_file)
        inps.dateList, inps.pbaseList = pnet.read_baseline_file(inps.bl_list_file)[0:2]
    print('number of acquisitions: {}'.format(len(inps.dateList)))

    # 2. Read All Date12/Ifgrams/Pairs
    inps.date12List = pnet.get_date12_list(inps.file)
    print('reading interferograms info from file: {}'.format(inps.file))
    print('number of interferograms: {}'.format(len(inps.date12List)))

    if inps.save_list:
        txtFile = os.path.splitext(os.path.basename(inps.file))[0]+'_date12List.txt'
        np.savetxt(txtFile, inps.date12List, fmt='%s')
        print('save pairs/date12 info to file: '+txtFile)

    # Optional: Read dropped date12 / date
    inps.dateList_drop = []
    inps.date12List_drop = []
    if ext in ['.h5', '.he5'] and k == 'ifgramStack':
        inps.date12List_keep = ifgramStack(inps.file).get_date12_list(dropIfgram=True)
        inps.date12List_drop = sorted(list(set(inps.date12List) - set(inps.date12List_keep)))
        print('-'*50)
        print('number of interferograms marked as drop: {}'.format(len(inps.date12List_drop)))
        print('number of interferograms marked as keep: {}'.format(len(inps.date12List_keep)))

        mDates = [i.split('_')[0] for i in inps.date12List_keep]
        sDates = [i.split('_')[1] for i in inps.date12List_keep]
        inps.dateList_keep = sorted(list(set(mDates + sDates)))
        inps.dateList_drop = sorted(list(set(inps.dateList) - set(inps.dateList_keep)))
        print('number of acquisitions marked as drop: {}'.format(len(inps.dateList_drop)))
        if len(inps.dateList_drop) > 0:
            print(inps.dateList_drop)

    # Optional: Read Coherence List
    inps.cohList = None
    if ext in ['.h5', '.he5'] and k == 'ifgramStack':
        inps.cohList, cohDate12List = ut.spatial_average(inps.file, datasetName='coherence', maskFile=inps.maskFile,
                                                         saveList=True, checkAoi=False)
        if all(np.isnan(inps.cohList)):
            inps.cohList = None
            print('WARNING: all coherence value are nan! Do not use this and continue.')

        if set(cohDate12List) > set(inps.date12List):
            print('extract coherence value for all pair/date12 in input file')
            inps.cohList = [inps.cohList[cohDate12List.index(i)] for i in inps.date12List]
        elif set(cohDate12List) < set(inps.date12List):
            inps.cohList = None
            print('WARNING: not every pair/date12 from input file is in coherence file')
            print('turn off the color plotting of interferograms based on coherence')
    return inps


##########################  Main Function  ##############################
def main(iargs=None):
    inps = cmd_line_parse(iargs)
    inps = read_network_info(inps)

    # Plot
    if not inps.disp_fig:
        plt.switch_backend('Agg')
    inps.cbar_label = 'Average Spatial Coherence'
    figNames = [i+inps.fig_ext for i in ['BperpHistory', 'CoherenceMatrix', 'CoherenceHistory', 'Network']]

    # Fig 1 - Baseline History
    fig, ax = plt.subplots(figsize=inps.fig_size)
    ax = pp.plot_perp_baseline_hist(ax,
                                    inps.dateList,
                                    inps.pbaseList,
                                    vars(inps),
                                    inps.dateList_drop)
    if inps.save_fig:
        fig.savefig(figNames[0], bbox_inches='tight', transparent=True, dpi=inps.fig_dpi)
        print('save figure to {}'.format(figNames[0]))

    if inps.cohList is not None:
        # Fig 2 - Coherence Matrix
        fig, ax = plt.subplots(figsize=inps.fig_size)
        ax = pp.plot_coherence_matrix(ax,
                                      inps.date12List,
                                      inps.cohList,
                                      inps.date12List_drop,
                                      plot_dict=vars(inps))[0]
        if inps.save_fig:
            fig.savefig(figNames[1], bbox_inches='tight', transparent=True, dpi=inps.fig_dpi)
            print('save figure to {}'.format(figNames[1]))

        # Fig 3 - Min/Max Coherence History
        fig, ax = plt.subplots(figsize=inps.fig_size)
        ax = pp.plot_coherence_history(ax,
                                       inps.date12List,
                                       inps.cohList,
                                       plot_dict=vars(inps))
        if inps.save_fig:
            fig.savefig(figNames[2], bbox_inches='tight', transparent=True, dpi=inps.fig_dpi)
            print('save figure to {}'.format(figNames[2]))

    # Fig 4 - Interferogram Network
    fig, ax = plt.subplots(figsize=inps.fig_size)
    ax = pp.plot_network(ax,
                         inps.date12List,
                         inps.dateList,
                         inps.pbaseList,
                         vars(inps),
                         inps.date12List_drop)
    if inps.save_fig:
        fig.savefig(figNames[3], bbox_inches='tight', transparent=True, dpi=inps.fig_dpi)
        print('save figure to {}'.format(figNames[3]))

    if inps.disp_fig:
        print('showing ...')
        plt.show()


############################################################
if __name__ == '__main__':
    main()
