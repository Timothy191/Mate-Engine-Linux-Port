# Professional Avatar Workflow Guide

This document synthesizes the findings from the **Avatar Research Agent Fleet**, detailing the industry-standard pipelines for crafting, refining, and integrating professional-grade 3D avatars (VRM/Unity workflows).

## 1. Mesh Topology & Optimization
*Synthesized by `avatar-mesh-texture-researcher`*

- **Quad-based Topology**: All deformable areas (joints, face) must be built using quad-based polygons to ensure smooth, artifact-free bending and expression morphing.
- **Edge Loops**: Focus circular edge loops around the eyes, mouth, shoulders, elbows, and knees. 
- **Decimation & Retopology**:
  - High-poly sculpts (from ZBrush or Blender) must be retopologized. 
  - Target polycount for real-time mobile/VR is **10,000 - 30,000 triangles**. For desktop/high-end, **50,000 - 70,000 triangles** is optimal.
  - Hidden meshes (body underneath non-removable clothing) should be deleted to save rendering overhead and prevent clipping.

## 2. Texturing & UV Mapping
*Synthesized by `avatar-mesh-texture-researcher`*

- **PBR Workflow**: Utilize Physically Based Rendering (PBR) textures (Albedo, Normal, Metallic/Smoothness, Ambient Occlusion).
- **UV Packing**: Pack UVs efficiently into square textures (typically 2048x2048 or 4096x4096). Keep seams in hidden areas (e.g., inner seams of arms/legs, back of the head).
- **Texture Atlasing**: Combine multiple materials into a single Texture Atlas (using tools like CATS Blender Plugin or Material Combiner) to drastically reduce draw calls in Unity.

## 3. Rigging & Bone Hierarchies
*Synthesized by `avatar-rigging-researcher`*

- **Standardization**: Ensure the armature follows the **Unity Humanoid** naming convention (e.g., `Hips`, `Spine`, `Chest`, `UpperChest`, `Neck`, `Head`). This is critical for animation retargeting.
- **T-Pose**: The character must be modeled and rigged in a strict T-Pose (arms perfectly straight, palms facing down/forward) for the cleanest IK retargeting.
- **Weight Painting**:
  - Keep influence to a maximum of **4 bones per vertex** (Unity's hardware skinning limit).
  - Smooth weights at joints to prevent the "candy wrapper" effect when twisting limbs.

## 4. Blendshapes (Morph Targets) & Expressions
*Synthesized by `avatar-animation-blendshape-researcher`*

- **ARKit 52 Standard**: For professional facial tracking and lip-syncing, implement the 52 standard ARKit blendshapes (e.g., `jawOpen`, `eyeBlinkLeft`, `mouthSmileRight`).
- **VRM Blendshape Proxy**: If using the VRM format, map basic expressions (`Joy`, `Angry`, `Sorrow`, `Fun`, `Neutral`) and visemes (`A`, `I`, `U`, `E`, `O`) in the VRM BlendShapeAvatar asset.
- **Normal Calculation**: Ensure blendshapes do not break vertex normals; recalculate normals dynamically if severe clipping or shading artifacts occur during expressions.

## 5. Export & Unity Integration

1. **Format**: Export as `.FBX` (for standard Unity workflows) or `.VRM` (for standard Vtuber/Metaverse applications).
2. **Import Settings**:
   - Rig -> Animation Type: `Humanoid`.
   - Materials -> Extract Materials (set to standard Unity lit/unlit shaders or MToon for anime styling).
3. **MateEngine Integration**: Use the `VRMLoader` component to dynamically load these optimized `.vrm` files at runtime, leveraging the sub-1.2s preview pipeline.
