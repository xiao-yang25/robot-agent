"""Single controlled status-panel interpreter, independent of fixture state."""
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class MarkerReading:
    """Pixel-free diagnostic of one controlled panel, not an execution grant."""
    classification: str
    reason: str | None
    region: tuple | None
    color_fraction: float = 0.
    white_border_fraction: float = 0.
    profile: str = 'located-white-panel-v1'


def read_marker(frame):
    """Locate one near-frontal white-bordered panel in immutable 640x480 RGB.

    A connected white frame defines the region before color interpretation. The
    inner rectangle is a fixed proportion of that frame, never fitted to pure
    color. This controlled profile cannot authenticate a target or recover a
    clipped panel; the caller still owns station/source/time association.
    """
    width, height = 640, 480
    if ((frame.width, frame.height, frame.encoding) != (width, height, 'rgb8')
            or not isinstance(frame.pixels, bytes) or len(frame.pixels) != width*height*3):
        raise ValueError('unsupported status-marker image')
    # 0=other, 1=green, 2=red, 3=white. Fixed image size bounds work and memory.
    pixels, mask = frame.pixels, bytearray(width*height)
    for index in range(width*height):
        offset = index*3
        r, g, b = pixels[offset:offset+3]
        if min(r, g, b) > 150 and max(r, g, b)-min(r, g, b) < 35:
            mask[index] = 3
        elif g > 80 and g > r*2 and g > b*2:
            mask[index] = 1
        elif r > 80 and r > g*2 and r > b*2:
            mask[index] = 2
    visited, candidates, components = bytearray(width*height), [], 0
    for start in range(width*height):
        if mask[start] != 3 or visited[start]:
            continue
        components += 1
        if components > 128:
            return MarkerReading('unknown', 'scene_too_complex', None)
        queue = deque([start])
        visited[start] = 1
        left = right = start % width
        top = bottom = start // width
        count = 0
        while queue:
            index = queue.popleft()
            y, x = divmod(index, width)
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            count += 1
            for neighbor in (index-1 if x else -1, index+1 if x+1 < width else -1,
                             index-width if y else -1, index+width if y+1 < height else -1):
                if neighbor >= 0 and mask[neighbor] == 3 and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
        w, h = right-left+1, bottom-top+1
        # A substantial white fragment at the image edge may be a second
        # clipped panel. Do not discard it by the full-panel size/aspect filter.
        if (count >= 20 and max(w, h) >= 20
                and (left <= 1 or top <= 1 or right >= width-2 or bottom >= height-2)):
            return MarkerReading('unknown', 'view_ambiguous_at_image_edge',
                                 (left, top, right+1, bottom+1))
        if w < 80 or h < 60 or not .9 <= w/h <= 3. or count/(w*h) > .8:
            continue
        candidates.append((left, top, right+1, bottom+1))
        if len(candidates) > 1:
            return MarkerReading('unknown', 'target_not_unique', None)
    if not candidates:
        return MarkerReading('unknown', 'target_not_located', None)
    left, top, right, bottom = candidates[0]
    region = (left, top, right, bottom)
    w, h = right-left, bottom-top
    if left <= 1 or top <= 1 or right >= width-1 or bottom >= height-1:
        return MarkerReading('unknown', 'target_clipped_or_border_incomplete', region)
    if w > 560 or h > 400:
        return MarkerReading('unknown', 'target_scale_unsupported', region)

    def coverage(x1, y1, x2, y2, value):
        return sum(mask[y*width+x] == value for y in range(y1, y2)
                   for x in range(x1, x2))/((x2-x1)*(y2-y1))

    dx, dy = max(2, round(w*.12)), max(2, round(h*.18))
    borders = (coverage(left, top, left+dx, bottom, 3),
               coverage(right-dx, top, right, bottom, 3),
               coverage(left, top, right, top+dy, 3),
               coverage(left, bottom-dy, right, bottom, 3))
    border = min(borders)  # Each side must be present; total white area is insufficient.
    if border < .6:
        return MarkerReading('unknown', 'target_clipped_or_border_incomplete', region,
                             white_border_fraction=border)
    # White frames can touch and form one connected component. Count enclosed
    # non-white regions instead of equating white connectivity with one target.
    inset_x, inset_y = round(w*.12), round(h*.20)
    area = (left+inset_x, top+inset_y, right-inset_x, bottom-inset_y)
    holes, seen = 0, bytearray(w*h)
    for sy in range(top, bottom):
        for sx in range(left, right):
            slot = (sy-top)*w+sx-left
            if mask[sy*width+sx] == 3 or seen[slot]:
                continue
            queue = deque([(sx, sy)])
            seen[slot] = 1
            enclosed, area_count, intrudes = True, 0, False
            while queue:
                x, y = queue.popleft()
                area_count += 1
                if area[0] <= x < area[2] and area[1] <= y < area[3]:
                    intrudes = True
                if x in (left, right-1) or y in (top, bottom-1):
                    enclosed = False
                for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if not (left <= nx < right and top <= ny < bottom):
                        continue
                    neighbor = (ny-top)*w+nx-left
                    if not seen[neighbor] and mask[ny*width+nx] != 3:
                        seen[neighbor] = 1
                        queue.append((nx, ny))
            if not enclosed and intrudes and area_count >= 64:
                return MarkerReading('unknown', 'target_clipped_or_border_incomplete', region,
                                     white_border_fraction=border)
            if enclosed and area_count >= 64:
                holes += 1
                if holes > 1:
                    return MarkerReading('unknown', 'target_not_unique', region,
                                         white_border_fraction=border)
    if holes != 1:
        return MarkerReading('unknown', 'target_clipped_or_border_incomplete', region,
                             white_border_fraction=border)
    green, red = coverage(*area, 1), coverage(*area, 2)
    color = max(green, red)
    if min(green, red) > .05:
        return MarkerReading('unknown', 'conflicting_colors', region, color, border)
    if color < .7:
        return MarkerReading('unknown', 'color_evidence_insufficient', region, color, border)
    return MarkerReading('normal' if green > red else 'abnormal', None, region, color, border)


def classify(frame):
    if (frame.width != 640 or frame.height != 480 or frame.encoding != 'rgb8'
            or len(frame.pixels) != 640*480*3):
        raise ValueError('unsupported status-marker image')
    green = red = white = border_count = 0
    for y in range(100, 380):
        for x in range(180, 460):
            p = (y*640+x)*3
            r, g, b = frame.pixels[p:p+3]
            if abs(x-320) <= 64 and abs(y-240) <= 64:
                green += int(g > 80 and g > r*2 and g > b*2)
                red += int(r > 80 and r > g*2 and r > b*2)
            elif 110 <= max(abs(x-320), abs(y-240)) <= 139:
                border_count += 1
                white += int(min(r, g, b) > 150 and max(r, g, b)-min(r, g, b) < 35)
    color_fraction = max(red, green)/(129*129)
    border_fraction = white/border_count
    status = ('normal' if green > red else 'abnormal') if color_fraction >= .7 and border_fraction >= .1 else 'unknown'
    return status, color_fraction, border_fraction
