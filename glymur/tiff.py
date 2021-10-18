# 3rd party library imports
import numpy as np

# local imports
from glymur import Jp2k
from .lib import tiff as libtiff


class Tiff2Jp2k(object):
    """
    Attributes
    ----------
    tiff_filename : path or str
        Path to TIFF file.
    jp2_filename : path or str
        Path to JPEG 2000 file to be written.
    tilesize : tuple
        The dimensions of a tile in the JP2K file.
    """

    def __init__(self, tiff_filename, jp2_filename, tilesize=None):
        self.tiff_filename = tiff_filename
        self.jp2_filename = jp2_filename
        self.tilesize = tilesize

    def __enter__(self):
        self.tiff_fp = libtiff.open(self.tiff_filename)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        libtiff.close(self.tiff_fp)

    def run(self):

        if not libtiff.isTiled(self.tiff_fp):
            raise NotImplementedError('Not supported for stripped TIFFs')

        imagewidth = libtiff.getFieldDefaulted(self.tiff_fp, 'ImageWidth')
        imageheight = libtiff.getFieldDefaulted(self.tiff_fp, 'ImageLength')
        spp = libtiff.getFieldDefaulted(self.tiff_fp, 'SamplesPerPixel')
        sf = libtiff.getFieldDefaulted(self.tiff_fp, 'SampleFormat')
        bps = libtiff.getFieldDefaulted(self.tiff_fp, 'BitsPerSample')
        tw = libtiff.getFieldDefaulted(self.tiff_fp, 'TileWidth')
        th = libtiff.getFieldDefaulted(self.tiff_fp, 'TileLength')

        if (
            tw > imagewidth
            and th > imageheight
            and libtiff.RGBAImageOK(self.tiff_fp)
        ):
            image = libtiff.readRGBAImageOriented(self.tiff_fp)

            if spp < 4:
                image = image[:, :, :3]

            Jp2k(self.jp2_filename, data=image)

        elif (
            (imagewidth % tw) == 0
            and (imageheight % th) == 0
            and bps == 8
            and sf == libtiff.SampleFormat.UINT
            and self.tilesize is None
        ):

            # The image is evenly tiled uint8.  This is ideal.
            tile = np.zeros((th, tw, spp), dtype=np.uint8)
            jp2 = Jp2k(
                self.jp2_filename,
                shape=(imageheight, imagewidth, spp),
                tilesize=(th, tw)
            )
            for idx, tilewriter in enumerate(jp2.get_tilewriters()):
                libtiff.readEncodedTile(self.tiff_fp, idx, tile)
                tilewriter[:] = tile

        elif (
            (imagewidth % tw) == 0
            and (imageheight % th) == 0
            and bps == 8
            and sf == libtiff.SampleFormat.UINT
            and self.tilesize is not None
            and imageheight % self.tilesize[0] == 0
            and imagewidth % self.tilesize[1] == 0
        ):

            jth, jtw = self.tilesize

            # The input image is evenly tiled uint8, but the output image
            # tiles evenly subtile the input image tiles
            tile = np.zeros((th, tw, spp), dtype=np.uint8)
            jp2 = Jp2k(
                self.jp2_filename,
                shape=(imageheight, imagewidth, spp),
                tilesize=self.tilesize,
            )

            num_jp2k_tile_rows = imageheight // jth
            num_jp2k_tile_cols = imagewidth // jtw

            num_tiff_tile_rows = imageheight // th
            num_tiff_tile_cols = imagewidth // tw

            jp2k_tile = np.zeros((jth, jtw, spp), dtype=np.uint8)
            tiff_tile = np.zeros((th, tw, spp), dtype=np.uint8)

            for idx, tilewriter in enumerate(jp2.get_tilewriters()):

                jp2k_tile_row = idx // num_jp2k_tile_cols
                jp2k_tile_col = idx % num_jp2k_tile_cols

                jrow = jp2k_tile_row * jth
                jcol = jp2k_tile_col * jtw

                # the coordinates of the upper left pixel of the jp2k tile
                julr, julc = jp2k_tile_row * jth, jp2k_tile_col * jtw

                # populate the jp2k tile with tiff tiles
                for y in range(julr, min(julr + jth, imageheight), th):
                    for x in range(julc, min(julc + jtw, imagewidth), tw):
                        tilenum = libtiff.computeTile(
                            self.tiff_fp, x, y, 0, 0
                        )
                        libtiff.readEncodedTile(
                            self.tiff_fp, tilenum, tiff_tile
                        )

                        tiff_tile_row = tilenum // num_tiff_tile_cols
                        tiff_tile_col = tilenum % num_tiff_tile_cols

                        # the coordinates of the upper left pixel of the TIFF
                        # tile
                        tulr = tiff_tile_row * th
                        tulc = tiff_tile_col * tw

                        # determine how to fit this tiff tile into the jp2k
                        # tile
                        #
                        # these are the section coordinates in image space
                        ulr = max(julr, tulr)
                        llr = min(julr + jth, tulr + th)

                        ulc = max(julc, tulc)
                        urc = min(julc + jtw, tulc + tw)

                        # convert to JP2K tile coordinates
                        j2k_rows = slice(ulr % jth, (llr - 1) % jth + 1)
                        j2k_cols = slice(ulc % jtw, (urc - 1) % jtw + 1)

                        # convert to TIFF tile coordinates
                        tiff_rows = slice(ulr % th, (llr - 1) % th + 1)
                        tiff_cols = slice(ulc % tw, (urc - 1) % tw + 1)

                        try:
                            jp2k_tile[j2k_rows, j2k_cols, :] = tiff_tile[tiff_rows, tiff_cols, :]
                        except ValueError:
                            breakpoint()
                            raise

                tilewriter[:] = jp2k_tile
