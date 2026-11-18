"""Shared axis-aligned SVG geometry for layout checking and PPT export."""
import re


def parse_axis_aligned_transform(transform):
    """Compose one SVG transform string's translate/scale operations without losing nested offsets.

    这是本包的**唯一坐标模型**。检查画面（validate_svg_layout）必须从这里取，
    不允许自己再写一份——两份曾经分歧到同一份输入差 100px。
    """
    sx = sy = 1.0
    ox = oy = 0.0
    for name, raw_args in re.findall(r"(translate|scale)\s*\(([^)]*)\)", transform or ""):
        values = [float(value) for value in re.findall(r"[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?", raw_args)]
        if not values:
            continue
        if name == "translate":
            tx = values[0]
            ty = values[1] if len(values) > 1 else 0.0
            ox += sx * tx
            oy += sy * ty
        else:
            sx *= values[0]
            sy *= values[1] if len(values) > 1 else values[0]
    return ox, oy, sx, sy


def compose_axis_aligned(parent, local):
    """(ox,oy,sx,sy) of an outer transform composed with an inner one.

    这是 add_elements 在 <g> 递归里实际使用的合成规则，也是检查画面沿祖先链
    累计时必须用的同一条规则。
    """
    ox, oy, sx, sy = parent
    local_ox, local_oy, local_sx, local_sy = local
    return ox + sx * local_ox, oy + sy * local_oy, sx * local_sx, sy * local_sy
