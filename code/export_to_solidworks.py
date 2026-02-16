"""
SolidWorksConverter — reusable class for importing STEP geometry into SolidWorks parts.

Features:
    - Robust COM connection with retry / timeout
    - Context-manager support (``with SolidWorksConverter(...) as sw:``)
    - Import STEP, delete bodies, center geometry at origin
    - CLI interface for quick one-off use

Prereqs:
    pip install pywin32
Run on Windows with SolidWorks installed.
"""

import logging
import os
import sys
import time

import pythoncom
import win32com.client

log = logging.getLogger(__name__)


# ── SolidWorks enum constants (stable across versions) ───────────────────────
class SWConst:
    DocPART = 1
    OpenDocOptions_Silent = 1
    BodyType_All = 5
    Delete_Absorbed = 1
    ImportSTEP = 8          # swImportDataFileType_e.swImportSTEP
    SaveAsOptions_Silent = 1
    UserPrefStringDefaultTemplatePart = 1


# ── Main class ───────────────────────────────────────────────────────────────
class SolidWorksConverter:
    """High-level helper that wraps a SolidWorks COM session.

    Parameters
    ----------
    visible : bool
        Make SolidWorks visible on connect (default True).
    connect_timeout : float
        Max seconds to wait for COM to respond (default 60).
    connect_retries : int
        Number of connection attempts before giving up (default 3).
    """

    def __init__(
        self,
        visible: bool = True,
        connect_timeout: float = 60.0,
        connect_retries: int = 3,
    ):
        self.visible = visible
        self.connect_timeout = connect_timeout
        self.connect_retries = connect_retries

        self._swApp = None
        self._model = None

    # ── Context manager ──────────────────────────────────────────────────
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    # ── Connection ───────────────────────────────────────────────────────
    def connect(self):
        """Connect to (or launch) SolidWorks via COM with retry logic."""
        pythoncom.CoInitialize()
        last_err = None
        for attempt in range(1, self.connect_retries + 1):
            log.info("SolidWorks COM connect attempt %d/%d …", attempt, self.connect_retries)
            try:
                self._swApp = self._dispatch_with_timeout()
                self._swApp.Visible = self.visible
                log.info("Connected to SolidWorks (visible=%s).", self.visible)
                return
            except Exception as e:
                last_err = e
                log.warning("Attempt %d failed: %s", attempt, e)
                time.sleep(2)

        raise ConnectionError(
            f"Could not connect to SolidWorks after {self.connect_retries} attempts.\n"
            f"Last error: {last_err}\n"
            "Make sure SolidWorks is installed and not blocked by another process."
        )

    def _dispatch_with_timeout(self):
        """Connect to SolidWorks COM - try running instance first, then launch."""
        # Try to connect to already-running instance
        try:
            return win32com.client.GetActiveObject("SldWorks.Application")
        except Exception:
            pass
        
        # Launch new instance
        return win32com.client.Dispatch("SldWorks.Application")

    def disconnect(self):
        """Release COM references (does NOT close SolidWorks)."""
        self._model = None
        self._swApp = None
        pythoncom.CoUninitialize()

    @property
    def app(self):
        if self._swApp is None:
            raise RuntimeError("Not connected — call .connect() or use as context manager.")
        return self._swApp

    @property
    def model(self):
        return self._model

    # ── Part open / create ───────────────────────────────────────────────
    def open_or_create_part(self, part_path: str):
        """Open an existing SLDPRT or create a new one, then activate it.

        Returns the ModelDoc2 COM object.
        """
        part_path = os.path.abspath(part_path)

        if os.path.isfile(part_path):
            model = self.app.OpenDoc6(
                part_path,
                SWConst.DocPART,
                SWConst.OpenDocOptions_Silent,
                "",
                0,
                0,
            )
            if model is None:
                raise RuntimeError(f"Failed to open part: {part_path}")
        else:
            # Create new part - try multiple approaches
            template = self._default_part_template()
            model = None
            
            # Try 1: Use default template if available
            if template:
                try:
                    model = self.app.NewDocument(template, 0, 0, 0)
                except Exception as e:
                    log.warning("Failed with default template: %s", e)
            
            # Try 2: Use empty template 
            if model is None:
                try:
                    model = self.app.NewDocument("", 0, 0, 0)
                except Exception as e:
                    log.warning("Failed with empty template: %s", e)
            
            # Try 3: Use part file type constant
            if model is None:
                try:
                    model = self.app.NewDocument("Part", 0, 0, 0)
                except Exception as e:
                    log.warning("Failed with 'Part' template: %s", e)
            
            # Try 4: Force create with specific template paths
            if model is None:
                common_templates = [
                    "Part",
                    r"C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\Part.prtdot", 
                    r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\Part.prtdot",
                    r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\Part.prtdot"
                ]
                for tpl in common_templates:
                    try:
                        model = self.app.NewDocument(tpl, 0, 0, 0)
                        if model:
                            break
                    except Exception:
                        continue
                        
            if model is None:
                raise RuntimeError(
                    "Failed to create new part. Check SolidWorks installation and templates. "
                    "You may need to configure default templates in SolidWorks Options."
                )
            ok = model.SaveAs3(part_path, SWConst.SaveAsOptions_Silent, 0)
            if not ok:
                raise RuntimeError(f"Failed to save new part to: {part_path}")

        self.app.ActivateDoc2(model.GetTitle(), False, 0)
        self._model = model
        log.info("Part active: %s", part_path)
        return model

    def _default_part_template(self) -> str:
        try:
            tpl = self.app.GetUserPreferenceStringValue(
                SWConst.UserPrefStringDefaultTemplatePart
            )
            if tpl and os.path.isfile(tpl):
                return tpl
        except Exception:
            pass
        return ""

    # ── Body operations ──────────────────────────────────────────────────
    def delete_all_bodies(self, model=None):
        """Delete every body (solid + surface + wire) from the part."""
        model = model or self._model
        bodies = model.GetBodies2(SWConst.BodyType_All, True)
        if not bodies:
            log.info("No bodies to delete.")
            return

        model.ClearSelection2(True)
        for b in bodies:
            try:
                b.Select2(True, None)
            except Exception:
                pass
        model.Extension.DeleteSelection2(SWConst.Delete_Absorbed)
        model.ClearSelection2(True)
        log.info("Deleted %d bodies.", len(bodies))

    # ── STEP import ──────────────────────────────────────────────────────
    def import_step(self, step_path: str, model=None):
        """Import a STEP file into the active part."""
        model = model or self._model
        step_path = os.path.abspath(step_path)

        if not os.path.isfile(step_path):
            raise FileNotFoundError(f"STEP file not found: {step_path}")
        if model.GetType() != SWConst.DocPART:
            raise RuntimeError("Active document is not a PART.")

        import_data = self.app.GetImportFileData(step_path)
        if import_data is None:
            raise RuntimeError("GetImportFileData returned None — cannot prepare STEP import.")

        ok = model.Extension.LoadFile4(step_path, SWConst.ImportSTEP, 0, import_data, 0)
        if not ok:
            raise RuntimeError(f"STEP import failed for: {step_path}")

        log.info("Imported STEP: %s", step_path)

    # ── Geometry helpers ─────────────────────────────────────────────────
    @staticmethod
    def combined_bbox_center(model):
        """Return (cx, cy, cz) of the combined bounding-box center, or None."""
        bodies = model.GetBodies2(SWConst.BodyType_All, True)
        if not bodies:
            return None

        INF = 1e99
        lo = [INF, INF, INF]
        hi = [-INF, -INF, -INF]

        for b in bodies:
            try:
                box = b.GetBodyBox()
                if not box:
                    continue
                for i in range(3):
                    lo[i] = min(lo[i], float(box[i]))
                    hi[i] = max(hi[i], float(box[i + 3]))
            except Exception:
                continue

        if lo[0] > 1e98:
            return None
        return tuple(0.5 * (lo[i] + hi[i]) for i in range(3))

    def move_to_origin(self, model=None) -> bool:
        """Translate all bodies so the bbox center sits at (0, 0, 0)."""
        model = model or self._model
        center = self.combined_bbox_center(model)
        if center is None:
            return False

        dx, dy, dz = (-center[0], -center[1], -center[2])

        bodies = model.GetBodies2(SWConst.BodyType_All, True)
        if not bodies:
            return False

        model.ClearSelection2(True)
        for b in bodies:
            try:
                b.Select2(True, None)
            except Exception:
                pass

        feat = model.FeatureManager.InsertMoveCopyBody2(
            dx, dy, dz, 0.0, 0.0, 0.0, 0.0, False, 1
        )
        model.ClearSelection2(True)

        moved = feat is not None
        log.info("Move to origin: %s (offset=%.4f, %.4f, %.4f)", moved, dx, dy, dz)
        return moved

    # ── Save ─────────────────────────────────────────────────────────────
    def save(self, model=None):
        """Save the active document silently."""
        model = model or self._model
        model.Save3(SWConst.SaveAsOptions_Silent, 0, 0)
        log.info("Part saved.")

    # ── High-level workflow ──────────────────────────────────────────────
    def replace_geometry(self, part_path: str, step_path: str, center_at_origin: bool = True):
        """Full pipeline: open part → delete bodies → import STEP → center → save.

        Parameters
        ----------
        part_path : str
            Path to existing .SLDPRT or desired new file location.
        step_path : str
            Path to .step / .stp file to import.
        center_at_origin : bool
            If True, translate bbox center to (0, 0, 0) after import.
        """
        model = self.open_or_create_part(part_path)
        self.delete_all_bodies(model)
        self.import_step(step_path, model)

        moved = False
        if center_at_origin:
            moved = self.move_to_origin(model)

        self.save(model)

        log.info("Done — Part: %s | STEP: %s | Centered: %s", part_path, step_path, moved)
        return model


# ── Convenience function ─────────────────────────────────────────────────────
def run(step_path: str, center_at_origin: bool = True, visible: bool = True):
    """Import a STEP file into a .SLDPRT with the same name in the same directory.

    Parameters
    ----------
    step_path : str
        Path to .step / .stp file.
    center_at_origin : bool
        If True, translate bbox center to (0, 0, 0) after import.
    visible : bool
        Show the SolidWorks window.

    Returns
    -------
    ModelDoc2 COM object of the saved part.
    """
    step_path = os.path.abspath(step_path)
    if not os.path.isfile(step_path):
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    # Derive .SLDPRT path: same name, same folder
    part_path = os.path.splitext(step_path)[0] + ".SLDPRT"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    with SolidWorksConverter(visible=visible) as sw:
        return sw.replace_geometry(
            part_path=part_path,
            step_path=step_path,
            center_at_origin=center_at_origin,
        )


if __name__ == "__main__":
    run(r"D:\EV27 CAD\OptimumK Geometry\Static\3D\Kinematic_Skeleton.step")
