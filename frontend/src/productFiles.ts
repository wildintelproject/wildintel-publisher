import type { ProductType } from './types'

/** What a repository's "Prepared package" output holds of the product itself
 * (see each adapter's extract_core_files in the backend) — worded per
 * product type, so a dataset isn't described with another one's files.
 * `imagesSeparate`: the images are a heavy extra the output leaves out
 * (Camtrap DP's media live at URLs); for an AI dataset they ARE the dataset. */
export function preparedCoreFiles(productType: ProductType | null | undefined): { what: string; imagesSeparate: boolean } {
  switch (productType) {
    case 'yolo':
      return { what: 'the dataset files (data.yaml, images/, labels/)', imagesSeparate: false }
    case 'software':
      return { what: "the application's own files", imagesSeparate: false }
    case 'camtrapdp':
    case null:
    case undefined:
      return { what: 'the Camtrap DP files (datapackage.json, deployments.csv, media.csv, observations.csv)', imagesSeparate: true }
    default:
      return { what: "the product's own files", imagesSeparate: false }
  }
}
