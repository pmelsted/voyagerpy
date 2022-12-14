#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Nov 25 14:08:42 2022

@author: sinant
"""


from math import ceil
from typing import (
    Any,
    Dict,
    Collection,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import geopandas as gpd
import numpy as np

from anndata import AnnData
from copy import deepcopy
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from pandas import options

options.mode.chained_assignment = None  # default='warn'
from voyagerpy import spatial as spt

plt.style.use("ggplot")


def plot_features(adata: AnnData, x: str, y: str, colour_by: Optional[str] = None, cmap: str = "viridis", alpha: float = 0.6, ax: Optional[Axes] = None) -> Any:

    import matplotlib as mpl
    from cycler import cycler

    mpl.rcParams["axes.prop_cycle"] = cycler(
        "color", ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    )
    mpl.rcParams["lines.markersize"] = 3
    mpl.rcParams["legend.frameon"] = False
    mpl.rcParams["legend.shadow"] = False
    fig, ax = plt.subplots()

    kwargs = {"alpha": alpha}
    if colour_by is not None:

        color_vals = sorted(set(adata.obs[colour_by].to_list()))
        is_binary = len(color_vals) == 2
        is_binary = is_binary and (color_vals == [0, 1] or color_vals == [False, True])

        for val in color_vals:
            subdata = adata.obs[adata.obs[colour_by] == val]
            label = str(bool(val)).upper() if is_binary else val
            ax.scatter(subdata[x], subdata[y], **kwargs, label=label)

        ax.legend(loc=(1.04, 0.5), title=colour_by)

    else:
        ax.scatter(adata.obs[x], adata.obs[y], **kwargs)

    return ax


def plot_bin2d(
        data: Union[AnnData, 'pd.DataFrame'], x: str, y: str, filt: Optional[str] = None, subset: Optional[str] = None,
        bins: int = 100, name_true: Optional[str] = None, name_false: Optional[str] = None,
        hex_plot: bool = False, binwidth: Optional[float] = None, **kwargs
):

    get_dataframe = lambda df: df.obs if x in df.obs and y in df.obs else df.var
    obs = get_dataframe(data) if isinstance(data, AnnData) else data

#     I don't know how the range is computed in ggplot2
#     r = ((-6.377067e-05,  4.846571e+04), (-1.079733e-05, 8.205973e+03))
    r = None

    plot_kwargs = dict(
        bins=bins,
        cmap='Blues',
        range=r,
    )

    figsize = kwargs.pop('figsize', (10, 7))
    plot_kwargs.update(kwargs)

    grid_kwargs = dict(
            visible=True,
            which='both',
            axis='both',
            color='k',
            linewidth=0.5,
            alpha=0.2
    )

    if hex_plot:
        renaming = [
            ('gridsize', 'bins', bins),
            ('extent', 'range', None),
            ('mincnt', 'cmin', 1),
        ]
        for hex_name, hist_name, default in renaming:
            val = plot_kwargs.pop(hist_name, default)
            plot_kwargs.setdefault(hex_name, val)

        plot_kwargs.setdefault('edgecolor', '#8c8c8c')
        plot_kwargs.setdefault('linewidth', 0.2)

    fig, ax = plt.subplots(figsize=figsize)
    plot_fun = ax.hexbin if hex_plot else ax.hist2d

    x = obs[x]
    y = obs[y]

    if subset is None:
        myfilt: Any = Ellipsis if filt is None else obs[filt].astype(bool)

        im = plot_fun(x[myfilt], y[myfilt], **plot_kwargs)  # type: ignore
        plt.colorbar(im[-1] if isinstance(im, tuple) else im)

    else:
        subset_name = subset
        name_true = name_true or subset_name
        name_false = name_false or f'!{subset_name}'

        subset_true = obs[subset].astype(bool)
        subset_false = (1 - subset_true).astype(bool)

        im1 = plot_fun(x[subset_false], y[subset_false], **plot_kwargs)

        plot_kwargs['cmap'] = 'Reds'
        im2 = plot_fun(x[subset_true], y[subset_true], **plot_kwargs)

        plt.colorbar(im1[-1] if isinstance(im1, tuple) else im1, label=name_true)
        plt.colorbar(im2[-1] if isinstance(im2, tuple) else im2, label=name_false)

    ax.grid(**grid_kwargs)
    ax.set_facecolor('w')
    return ax


def plot_features_bin2d(adata: AnnData, *args, **kwargs):
    return plot_bin2d(adata.var, *args, **kwargs)


def plot_barcodes_bin2d(adata: AnnData, *args, **kwargs):
    return plot_bin2d(adata.obs, *args, **kwargs)


def plot_spatial_features(
    adata: AnnData,
    features: Union[str, Sequence[str]],
    ncol: Optional[int] = None,
    barcode_geom: Optional[str] = None,
    annot_geom: Optional[str] = None,
    tissue: bool = True,
    colorbar: bool = False,
    color: Optional[str] = None,
    cmap: Optional[str] = "Blues",
    categ_type: Union[str, Collection[str]] = {},
    geom_style: Optional[Dict] = {},
    annot_style: Optional[Dict] = {},
    _ax: Optional[Axes] = None,
    subplot_kwds: Optional[Dict] = {},
    legend_kwds: Optional[Dict] = {},
    **kwds,
) -> Union[np.ndarray, Any]:

    if isinstance(features, list):
        feat_ls = features
    elif isinstance(features, str):
        feat_ls = [features]
    else:
        raise TypeError("features must be a string or a list of strings")

    # check input
    if ("geometry" not in adata.obs) or "geom" not in adata.uns["spatial"]:
        adata = spt.get_geom(adata)
    for i in feat_ls:
        if i not in adata.obs and i not in adata.var.index:
            raise ValueError(f"Cannot find {i!r} in adata.obs or gene names")
    # copy observation dataframe so we can edit it without changing the inputs
    obs = adata.obs

    # check if barcode geometry exists
    if barcode_geom is not None:
        if barcode_geom not in obs:
            raise ValueError(f"Cannot find {barcode_geom!r} data in adata.obs")

        # if barcode_geom is not spot polygons, change the default
        # geometry of the observation matrix, so we can plot it
        if barcode_geom != "spot_poly":
            obs.set_geometry(barcode_geom)

    # check if features are in rowdata

    # Check if too many subplots
    if len(feat_ls) > 6:
        raise ValueError("Too many features to plot, reduce the number of features")
    if ncol is not None:
        if ncol > 3:
            raise ValueError("Too many columns for subplots")

    # only work with spots in tissue
    if tissue:
        obs = obs[obs["in_tissue"] == 1]

    # create the subplots with right cols and rows
    if _ax is None:
        plt_nr = len(feat_ls)
        nrows = 1
        # ncols = ncol if ncol is not None else 1

        # defaults
        if ncol is None:
            if plt_nr < 4:
                ncols = plt_nr
            if plt_nr >= 4:
                nrows = 2
                ncols = 3

        else:
            nrows = ceil(plt_nr / ncols)

        # if(subplot_kwds is None):
        #     fig, axs = plt.subplots(nrows=nrows, ncols=ncols,figsize=(10,10))

        if "figsize" in subplot_kwds:
            fig, axs = plt.subplots(nrows=nrows, ncols=ncols, **subplot_kwds)
        else:

            # rat = row /col
            if nrows >= 2 and ncols == 3:
                _figsize = (10, 6)

            else:
                _figsize = (10, 10)
            fig, axs = plt.subplots(nrows=nrows, ncols=ncols, figsize=_figsize, **subplot_kwds)
            if plt_nr == 5:
                axs[-1, -1].axis("off")
        fig.tight_layout()  # Or equivalently,  "plt.tight_layout()"

        # plt.subplots_adjust(wspace = 1/ncols +  0.2)
    else:
        ncols = 1
        nrows = 1
        axs = _ax
    # iterate over features to plot
    x = 0
    y = 0

    for i in range(len(feat_ls)):
        legend_kwds_ = deepcopy(legend_kwds)

        if tissue:

            # if gene value
            if feat_ls[i] in adata.var.index:
                # col = adata.var[features]
                col = adata[adata.obs["in_tissue"] == 1, feat_ls[i]].X.todense().reshape((adata[adata.obs["in_tissue"] == 1, :].shape[0])).T

                col = np.array(col.ravel()).T
                obs[feat_ls[i]] = col
            if feat_ls[i] in obs.columns:
                # feat = features
                pass
        else:

            if feat_ls[i] in adata.var.index:
                # col = adata.var[features]
                col = adata[:, feat_ls[i]].X.todense().reshape((adata.shape[0])).T
                obs[feat_ls[i]] = col
            if feat_ls[i] in obs.columns:
                pass

        if ncols > 1 and nrows > 1:
            ax = axs[x, y]
        if ncols == 1 and nrows > 1:
            ax = axs[x]
        if nrows == 1 and ncols > 1:
            ax = axs[y]
        if ncols == 1 and nrows == 1:
            ax = axs

        # correct legend if feature is categorical and make sure title is in there
        if len(legend_kwds_) == 0:

            if feat_ls[i] in adata.var.index or adata.obs[feat_ls[i]].dtype != "category":
                legend_kwds_ = {
                    "label": feat_ls[i],
                    "orientation": "vertical",
                    "shrink": 0.3,
                }
            else:
                legend_kwds_ = {"title": feat_ls[i]}
        else:
            if feat_ls[i] in adata.var.index or adata.obs[feat_ls[i]].dtype != "category":
                legend_kwds_.setdefault("label", feat_ls[i])
                legend_kwds_.setdefault("orientation", "vertical")
                legend_kwds_.setdefault("shrink", 0.3)
            else:

                legend_kwds_.setdefault("title", feat_ls[i])

        if color is not None:
            cmap = None

        obs.plot(
            feat_ls[i],
            ax=ax,
            color=color,
            legend=True,
            cmap=cmap,
            legend_kwds=legend_kwds_,
            **geom_style,
            **kwds,
        )
        if annot_geom is not None:
            if annot_geom in adata.uns["spatial"]["geom"]:

                # check annot_style is dict with correct values
                plg = adata.uns["spatial"]["geom"][annot_geom]
                if len(annot_style) != 0:
                    gpd.GeoSeries(plg).plot(ax=ax, **annot_style, **kwds)
                else:
                    gpd.GeoSeries(plg).plot(color="blue", ax=ax, alpha=0.2, **kwds)
            else:
                raise ValueError(f"Cannot find {annot_geom!r} data in adata.uns['spatial']['geom']")

            pass

        y = y + 1
        if y >= ncols:
            y = 0
            x = x + 1
    # colorbar title
    if _ax is not None:
        fig = ax.get_figure()
    axs = fig.get_axes()
    for i in range(len(axs)):
        if axs[i].properties()["label"] == "<colorbar>":

            axs[i].set_title(axs[i].properties()["ylabel"], ha="left")
            axs[i].set_ylabel("")

    return axs  # ,fig
