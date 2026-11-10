# DINOv2 attribution and scope

This project's optional experimental shape adapter uses the **standard DINOv2
ViT-S/14 (LVD-142M)** backbone by Meta Platforms, Inc. and its research authors.
The DINOv2 backbone is not a model developed by PlayableSketch.

- Official source: https://github.com/facebookresearch/dinov2
- Source revision: `7764ea0f912e53c92e82eb78a2a1631e92725fc8`
- Standard model card: https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/MODEL_CARD.md
- Paper: Maxime Oquab et al., *DINOv2: Learning Robust Visual Features without Supervision*, 2023, https://arxiv.org/abs/2304.07193
- Standard code and backbone model license: **Apache License 2.0**. A copy is in
  `DINOv2-APACHE-2.0.txt`; original notices remain in the locally installed source.
- Weight SHA-256: `b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9`.

The backbone is frozen. The dense segmentation/keypoint decoder, local raw-ink
branch, masked supervision, graph adapter, evaluation and app integration are
project-authored additions. The backbone source and pretrained parameters are
unmodified; they are downloaded explicitly into `Saved/Dependencies/`. Runtime
inference is offline. The setup lock records source and weight hashes.

No XRay-DINO, Cell-DINO, dino.txt or pretrained semantic segmentation head is
used. Those separately published components must not be assumed to share this
standard backbone's licensing scope. No CubiCasa or Raster2Seq data/checkpoint
is used to train the project decoder.

This notice describes the third-party dependency; it does not grant rights to
unrelated third-party images, datasets, or the rest of this project's source.
