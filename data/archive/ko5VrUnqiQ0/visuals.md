# On-screen visuals — Exploring If Nvidia Can Beat Tesla's Self-Driving Cars

<https://www.youtube.com/watch?v=ko5VrUnqiQ0>

_Slides, charts, and diagrams read from the video by Claude vision. Text is transcribed from the screen and may contain OCR errors; not on-screen visuals are omitted._

## 1. [00:24] Autonomous vehicle camera feed visualization with multiple views showing vehicle detection, camera perspectives (Front Left, Front Center, Front Right, Rear Left, Rear Center, Rear Right), and on-screen metrics.

FPS: 10.90, Latency: 91.77 ms(avg), 105.57 ms(max), Frame #s, Timestamp, Sys Time, MAQ, GPS, Blindness percentages, Wide Front Center, Narrow Front Center, Rear positions with percentages

## 2. [00:43] NVIDIA visualization of extracted map features showing 3D point cloud data overlaid on street scene with light-colored 3D coordinate grid.

Extracted Map Features, NVIDIA logo

## 3. [00:46] 3D scene visualization showing automated scene generation at intersection with lane markings, crosswalks, and traffic infrastructure rendered in wireframe and solid geometry.

Automated 3D Scene Generation, NVIDIA logo

## 4. [01:49] Comparison of camera feed (top row) and LiDAR-based thermal/point cloud visualization (bottom) showing autonomous vehicle perception in various conditions.

LIVE

## 5. [02:01] PredictionNet diagram showing predicted vehicle trajectories in different colored paths, with real-world street scenes showing autonomous driving in urban environment.

PredictionNet, Anticipates other vehicles' behavior

## 6. [02:21] Technical overview slide showing 'Steps to Solve Automated 3D Labeling by Multi-trip Reconstruction' with step 1 'High Precision Trajectory' details and multiple road scene images with labeled annotations.

Steps to Solve Automated 3D Labeling by Multi-trip Reconstruction, 1. High Precision Trajectory, Input: Videos, Imu, Odometry, System: 2 cpu threads: tracking, optimization on inferences: feature extraction, Features: points, polylines, pano-seg, ground, Output: 6 dof trajectory @ 100hz, 3d structure and road detail, camera/sensor calibration, TESLA LIVE

## 7. [03:09] Technical slide showing step 2 'Multi-Trip Reconstruction' with internal steps and system details, featuring road scene imagery and 3D reconstruction visualization in purple/magenta.

Steps to Solve Automated 3D Labeling by Multi-trip Reconstruction, 1. High Precision Trajectory, 2. Multi-Trip Reconstruction, Internal Steps: Coarse Alignment, Pairwise Matching, Joint Optimization, Surface Refinement, System: parallelized on cluster, 1-2 hrs per reconstruction, TESLA LIVE

## 8. [04:03] Vector Space Encoding architecture diagram showing 'Language of Lanes' with neural network components (Self Attention, Cross Attention, Point Predictor, Topology Type Predictor) and lane center data visualization from aerial view.

Vector Space Encoding, Language of Lanes, Self Attention, Cross Attention, Point Predictor (level) → index: 9, Point Predictor (level2) → index: 22, Topology Type Predictor → -21.12, -3.8, -0.4, -1.9, TESLA LIVE

## 9. [04:43] Comparison table showing evolution of 3D labeling methods from 2018 to 2021+, with metrics for 3D label, reprojection, topology, labeling time, compute, scalability, and engineering effort.

image space (2018), single trip (2019), top-view (2020), multi-trip (2021-), 3D label: unknown/manual/aligned/reconstructed, reprojection: <1 pixel/<3 pixel/<7 pixel/<3 pixel, topology: local/up to trajectory/unlimited/up to reconstruction, Labeling/clip: 533 hrs/3.5 hrs/<0.1 hr (avg)/<0.1 hrs (avg), compute/clip: not needed/1 hr/2 hrs/0.5 hrs (avg), scalability: low/medium/high/very high, eng. effort: low/medium/high/very high, TESLA LIVE

## 10. [05:03] 3D map visualization showing lane structure with color-coded elements: higher speed lanes in red, lower speed lanes in green, lane centers and directions, radar point clouds, poles, signs, and traffic lights.

Higher Speed Lanes, Lower Speed Lanes, Lane Centers & Directions, Radar Point Clouds, Poles, Signs, Traffic Lights

## 11. [05:19] Multi-camera sensor fusion display showing 9 different vehicle camera views with bounding boxes and detection overlays, plus center 3D wireframe view of vehicle structure.

Machine-Learned Multi-Camera Fusion, End-to-end raw detections

## 12. [07:17] Technical architecture diagram showing occupancy grid features with street scene video context at top and 3D voxel space visualization with vehicle and building occupancy below.

Volumetric Occupancy, Multi-Camera & Video Context, Persistent Through Occlusions, Occupancy Semantics, Occupancy Flow, Resolution Where It Matters, Efficient Memory and Compute, Runs in ~10 Milliseconds, TESLA LIVE

## 13. [07:41] Street scene video frames at top with corresponding 3D occupancy grid visualization below showing spatial occupancy representation in blue (free) and red (occupied) voxels.

TESLA LIVE

## 14. [10:10] Continuation of technical slide showing 'Steps to Solve Automated 3D Labeling by Multi-trip Reconstruction' with step 2 details and large 3D reconstruction visualization in purple/magenta tones.

Steps to Solve Automated 3D Labeling by Multi-trip Reconstruction, 1. High Precision Trajectory, 2. Multi-Trip Reconstruction, Internal Steps: Coarse Alignment, Pairwise Matching, Joint Optimization, Surface Refinement, System: parallelized on cluster, 1-2 hrs per reconstruction, TESLA LIVE

## 15. [11:33] Tesla's autonomous driving pipeline architecture diagram showing five sequential stages: SENSE > PERCEIVE > MAP > PLAN > PILOT (highlighted in green), with tunnel driving scene and vehicle speed display (97 km/h) and safety indicators.

SENSE, PERCEIVE, MAP, PLAN, PILOT, 97 km/h

## 16. [12:44] Slide titled 'Ground Truth Alterations' showing comparison of annotated 3D scene structure (left) with real-world street intersection scene (right) featuring vehicles, pedestrians, and urban infrastructure.

Ground Truth Alterations

## 17. [12:57] Simulation World Creator architecture diagram showing workflow (Ground Truth Data → Tile Creator → Tile Extractor → Simulator/Instances → Tile Loader → Unreal Engine) with map of San Francisco area showing red and green tiles representing simulation coverage.

Simulation World Creator, SIMULATION WORLD CREATOR, Ground Truth Data, Tile Creator, Tile Extractor, Simulator, Instances, Tile Loader, Unreal Engine
