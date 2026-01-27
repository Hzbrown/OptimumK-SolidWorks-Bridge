import json
import pathlib
import cadquery as cq


class carAssembly:
    def __init__(self, path: str):
        self.name = path
        self.front_suspension, self.rear_suspension, self.setup = self._load_jsons(path)

    def _load_jsons(self, path: str):
        """Loads front and rear suspension JSON files from the given directory."""
        path = pathlib.Path(path)
        front_json_path = path / "Front_Suspension.json"
        rear_json_path = path / "Rear_Suspension.json"
        setup_json_path = path / "Vehicle_Setup.json"

        with open(front_json_path, "r") as f:
            front_suspension = json.load(f)
        with open(rear_json_path, "r") as f:
            rear_suspension = json.load(f)
        with open(setup_json_path, "r") as f:
            setup = json.load(f)

        return front_suspension, rear_suspension, setup

    def _draw_point(
        assy: cq.Assembly,
        name: str,
        xyz,
        size: float = 5.0,
        color=None,
    ):
        """
        Add a fixed point to an assembly as both a marker sphere and a small blue 'sketch point' sphere.

        Coloring rules:
        - If 'CHAS' in name: red
        - If 'UPRI' in name: green
        - If 'ROCK' in name: blue
        - Else: yellow
        """
        x, y, z = xyz

        # Determine color by name if not provided
        if color is None:
            if "CHAS" in name:
                color = (1.0, 0.0, 0.0)  # red
            elif "UPRI" in name:
                color = (0.0, 1.0, 0.0)  # green
            elif "ROCK" in name:
                color = (0.0, 0.0, 1.0)  # blue
            else:
                color = (1.0, 1.0, 0.0)  # yellow

        # Sphere marker
        pt = cq.Workplane("XY").sphere(size)
        # Small blue sphere as sketch point
        sketch_point = cq.Workplane("XY").sphere(size * 0.3).translate((0, 0, 0))

        # Add both to the assembly
        assy.add(
            pt,
            name=name + "_sphere",
            loc=cq.Location(cq.Vector(x, y, z)),
            color=cq.Color(*color),
        )
        assy.add(
            sketch_point,
            name=name + "_sketchpoint",
            loc=cq.Location(cq.Vector(x, y, z)),
            color=cq.Color(0, 0, 1),
        )

    def _draw_suspension(suspension: dict, name: str) -> cq.Assembly:
        """
        Draw all points from the JSON schema, rejecting any whose lists contain non-floats.
        """
        assy = cq.Assembly(name=name)

        def is_float_list(val):
            return (
                isinstance(val, list)
                and len(val) == 3
                and all(isinstance(x, (float, int)) for x in val)
            )

        # Traverse all groups and points in the JSON
        for group, points in suspension.items():
            if isinstance(points, dict):
                for pt_name, coords in points.items():
                    if is_float_list(coords):
                        carAssembly._draw_point(
                            assy,
                            f"{group}_{pt_name}",
                            coords,
                            size=3.0,
                        )

        carAssembly._draw_wheels(suspension.get("Wheels", {}), assy)

        return assy

    @staticmethod
    def _cylinder_between(p1, p2, radius=2.0) -> cq.Workplane | None:
        v1 = cq.Vector(*p1)
        v2 = cq.Vector(*p2)
        dv = (v2 - v1)/2
        L = dv.Length
        if L <= 1e-9:
            return None

        cyl = cq.Workplane("XY").circle(radius).extrude(L, both=True)

        z = cq.Vector(0, 0, 1)
        dirv = dv.normalized()
        axis = z.cross(dirv)
        axis_len = axis.Length

        if axis_len <= 1e-9:
            if z.dot(dirv) < 0:
                cyl = cyl.rotate((0, 0, 0), (1, 0, 0), 180)
        else:
            angle = z.getAngle(dirv)  # radians
            cyl = cyl.rotate((0, 0, 0), (axis.x, axis.y, axis.z), angle * 180.0 / 3.141592653589793)

        mid = (v1 + v2) * 0.5
        return cyl.translate((mid.x, mid.y, mid.z))

    @staticmethod
    def _draw_wishbones(suspension: dict, assembly: cq.Assembly) -> cq.Assembly:
        """
        Visualization-only wishbones from the 'Double A-Arm' point dictionary.
        Draws cylinders inside a Wishbones_VIS subassembly.
        """
        pts = suspension.get("Double A-Arm", {})
        vis = cq.Assembly(name="Wishbones_VIS")

        # arm_name -> list of (start_key_base, end_key_base)
        # Each pair becomes a cylinder. We'll append _L / _R.
        links = {
            "UpperArm": [
                ("CHAS_UppFor", "UPRI_UppPnt"),
                ("CHAS_UppAft", "UPRI_UppPnt"),
            ],
            "LowerArm": [
                ("CHAS_LowFor", "UPRI_LowPnt"),
                ("CHAS_LowAft", "UPRI_LowPnt"),
            ],
        }

        def get_pt(key: str):
            p = pts.get(key)
            return p if (isinstance(p, list) and len(p) == 3) else None

        for side in ("L", "R"):
            for arm_name, segs in links.items():
                for a_base, b_base in segs:
                    a = get_pt(f"{a_base}_{side}")
                    b = get_pt(f"{b_base}_{side}")
                    if a is None or b is None:
                        continue

                    body = carAssembly._cylinder_between(a, b, radius=2.0)
                    if body is None:
                        continue

                    vis.add(
                        body,
                        name=f"{arm_name}_{a_base}_to_{b_base}_{side}",
                        color=cq.Color(0.6, 0.6, 0.6),
                    )

        assembly.add(vis, name="Wishbones_VIS")
        return assembly

    @staticmethod
    def _draw_wheels(wheel: dict, assembly: cq.Assembly) -> cq.Assembly:
        """
        Draws two hollow black cylinders for left and right wheels.
        Assumes wheel["Half Track"][side] is already centerline -> wheel center distance.
        """
        for side in ("left", "right"):
            sign = 1.0 if side == "left" else -1.0

            tire_dia = float(wheel["Tire Diameter"][side])
            rim_dia = float(wheel["Rim Diameter"][side])
            width = float(wheel["Tire Width"][side])

            half_track = float(wheel["Half Track"][side])  # <-- NO /2
            lat_off = float(wheel["Lateral Offset"][side])
            lon_off = float(wheel["Longitudinal Offset"][side])
            vert_off = float(wheel["Vertical Offset"][side])

            camber = float(wheel["Static Camber"][side])  # deg
            toe = float(wheel["Static Toe"][side])  # deg

            # Wheel center position
            x_pos = lon_off
            y_pos = sign * (half_track + lat_off)
            z_pos = vert_off

            # Hollow cylinder centered about its extrusion axis
            tire = (
                cq.Workplane("XY")
                .circle(tire_dia / 2.0)
                .circle(rim_dia / 2.0)
                .extrude(width/2, both=True)  # Centered extrusion
            )

            # Extrude is along +Z; rotate so wheel axis is +Y
            tire = tire.rotate((0, 0, 0), (1, 0, 0), -90)

            # Apply camber (about +X) and toe (about +Z)
            tire = tire.rotate((0, 0, 0), (1, 0, 0), camber)
            tire = tire.rotate((0, 0, 0), (0, 0, 1), toe)

            # Place tire at correct 3D position
            tire = tire.translate((x_pos, y_pos, z_pos + tire_dia / 2.0))

            assembly.add(tire, name=f"Wheel_{side}", color=cq.Color(0, 0, 0))

        return assembly

    def draw(self, setup: dict) -> cq.Assembly:
        """Draws the car assembly with front and rear suspensions, offsetting rear by reference distance."""
        front_assy = carAssembly._draw_suspension(
            self.front_suspension, "Front Suspension"
        )
        front_assy = carAssembly._draw_wishbones(self.front_suspension, front_assy)
        rear_assy = carAssembly._draw_suspension(
            self.rear_suspension, "Rear Suspension"
        )
        rear_assy = carAssembly._draw_wishbones(self.rear_suspension, rear_assy)

        # Read reference distance from setup
        ref_dist = setup.get("Reference distance", 0)

        # Combine front and rear assemblies into a main assembly, offsetting rear
        main_assy = cq.Assembly(name="Car Assembly")
        main_assy.add(front_assy, name="Front Suspension")
        main_assy.add(
            rear_assy,
            name="Rear Suspension",
            loc=cq.Location(cq.Vector(-ref_dist, 0, 0)),
        )
        return main_assy


if __name__ == "__main__":
    assembly = carAssembly(r"results/Final EV2024")
    # Draw full car assembly
    car = assembly.draw(assembly.setup)

    # Save as STEP file
    car.save("Car_Assembly.step")
    print("Saved car assembly as Car_Assembly.step")

    # Show in ocp_vscode viewer if available
    try:
        from ocp_vscode import show_object

        show_object(car)
        print("Car assembly shown in ocp_vscode viewer.")
    except ImportError:
        print("ocp_vscode not available. Assembly not shown interactively.")
