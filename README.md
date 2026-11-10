# PlayableSketch

PlayableSketch turns a hand-drawn floor plan into an editable layout. It detects rooms and doors, lets you adjust shapes, connections and dimensions in the browser, and exports the approved plan for Unreal Engine.

## How it works

- **U-Net** extracts a pixel-level wall mask.
- **YOLO11n** detects door markers.
- Image processing temporarily closes the detected doors and identifies connected interior areas as rooms.
- The geometry step converts those areas into editable room boundaries.

Areas without a separating wall or door count as one room, including U-shaped and L-shaped spaces. There is no separate corridor class.

## Requirements

The browser workspace requires Python 3.13, the packages listed below and a current browser. The current setup has been run on macOS. It uses MPS on supported Apple Silicon hardware and CPU otherwise.

Opening or building the Unreal project also requires **Unreal Engine 5.7** and your platform's C++ build tools. Unreal Editor does not need to be running to upload drawings or edit plans.

## Setup

Clone the repository and open the project folder:

```bash
git clone https://github.com/xNgardy/PlayableSketch.git
cd PlayableSketch
```

On macOS, create the local Python environment:

```bash
python3.13 -m venv Saved/Runtime/hybrid-v1/python
source Saved/Runtime/hybrid-v1/python/bin/activate
python -m pip install --upgrade pip
python -m pip install torch==2.9.1 torchvision==0.24.1 ultralytics==8.4.208 numpy==2.4.2 opencv-python==4.13.0.92 shapely==2.2.0 scipy==1.18.1 jsonschema==4.26.0 Pillow==12.1.1
```

Model files are stored in `SketchPipeline/shape_authoring/models/hybrid-unet-yolo11-v1/`:

| File | Purpose |
| --- | --- |
| `wall.pt` | U-Net wall weights |
| `door.pt` | YOLO11n door weights |
| `model-lock.json` | Model file hashes and inference settings |

The active model and Python environment path are selected in `SketchPipeline/shape_authoring/workspace-model.lock.json`. Weight hashes are checked when the model loads.

## Starting the workspace

Run this from the project root:

```bash
Saved/Runtime/hybrid-v1/python/bin/python Scripts/start_runtime.py --workspace-only
```

The service starts and opens [http://127.0.0.1:8772/](http://127.0.0.1:8772/) in your browser.

On the prepared local installation, you can also double-click `Start Sketch Workspace.command`. This shortcut additionally expects the environment at `Saved/Training/v1/python/bin/python`; use the command above for a fresh installation.

To keep the service in the terminal, or run it on another operating system, use a Python environment with the required packages installed:

```bash
python -m SketchPipeline.shape_authoring.server \
  --port 8772 \
  --output Saved/ShapeFirst/workspace/jobs \
  --profile hybrid \
  --checkpoint SketchPipeline/shape_authoring/models/hybrid-unet-yolo11-v1/model-lock.json
```

Open the same address in your browser. Stop a service started this way with `Ctrl+C` in its terminal.

## From sketch to plan

1. Choose **Upload sketch** to upload a PNG or JPG, up to 20 MB. You can also drag the file onto the upload area.
2. Once detection finishes, check the result in the **Sketch**, **Plan** and **Compare** views.
3. Move and resize rooms, add missing rooms or doors, and delete incorrect suggestions.
4. Adjust room names and suggested dimensions, then choose **Save changes**.
5. Open **Review plan**, check the layout and confirm it.

Choose **Use a sample** to try the workspace without uploading a drawing. Previous drawings appear on the home screen and under **Saved drawings**. Switch between light and dark themes from the top bar.

### Preparing a drawing

Draw one floor from above. Keep wall lines clear. Mark a door by leaving a gap in the wall and adding a small tick at each end. Take the photo as straight-on as possible, with even lighting.

Written dimensions are optional. Suggested sizes are not measurements read from the drawing and can be changed later. Faint or broken lines can cause detection errors, so review the plan before exporting it.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `V` | Select / move |
| `R` | Add a room |
| `D` | Add a door |
| `G` | Add a connection |
| Arrow keys | Move the selected room, or resize it with the Resize tool |
| `Shift` + arrow keys | Use larger steps |
| `F` | Fit the plan to the view |
| `+` / `-` | Zoom in / out |
| `Ctrl/Cmd + S` | Save changes |
| `Ctrl/Cmd + Z` | Undo |
| `Delete` / `Backspace` | Delete the selected item |

## Exporting to Unreal Engine

**Review plan** offers two output modes:

- **Geometry only:** Exports room and door geometry.
- **Playable level:** Also requires a start and a goal in different rooms. Passages are checked for player clearance.

After confirming the plan, choose **Export for Unreal** to download a ZIP file. It contains `validated-layout.json`, plan provenance and a manifest with file hashes. If you change the geometry or dimensions, confirm the plan again.

If the Mac application has been built locally, open it with `Start PlayableSketch.command`. **Open latest plan** loads the latest playable export. Use WASD or the arrow keys to move, or choose **Follow route** to follow the route.

The packaged application is not included in the Git repository. To build the Unreal project, open `PlayableSketch.uproject` in Unreal Engine 5.7 and compile it. Mac packaging details are in the [packaging guide](Docs/step14_packaged_runtime.md).

## Project structure

| Folder / file | Contents |
| --- | --- |
| `SketchPipeline/shape_authoring/` | Model inference, geometry, local service and browser interface |
| `SketchPipeline/tests/` | Python tests |
| `Scripts/` | Training, evaluation, launch and packaging tools |
| `Source/` | Unreal Engine C++ code |
| `Content/`, `Config/` | Unreal assets and project settings |
| `Docs/` | Technical notes and evaluation reports |
| `Experiments/` | Protocols and results from earlier Unreal experiments |
| `Data/` | Local training data; excluded from Git |
| `Saved/` | Local environments, jobs, training and application outputs; excluded from Git |

Uploaded drawings, edits and exports are stored under `Saved/ShapeFirst/workspace/jobs/`. Deleting this folder also deletes the saved plans.

Training and experiment tools use separately prepared data, annotations and earlier experiment artifacts. These are not part of a fresh clone. Retraining is not required to run the application with the included weights.

## Checks and results

To check the hybrid integration, run this in the configured Python environment:

```bash
python -m unittest SketchPipeline.tests.test_hybrid_integration SketchPipeline.tests.test_project_model_selection
```

To run the full test suite:

```bash
python -m unittest discover -s SketchPipeline/tests
```

Some tests require local datasets, earlier model files and OCR dependencies. The application setup above does not provide everything needed for the full suite.

In the latest integration check, the L-shaped example produced **4 rooms / 3 doors**, and the U-shaped example produced **2 rooms / 1 door**. Both passed plan editing, sizing and geometry export checks. These are results for two examples, not an accuracy estimate across all drawings.

See the [training results](Docs/hybrid_unet_yolo11_training_2026_11_09.md) and [integration checks](Docs/hybrid_integration_2026_11_10.md) for details.
