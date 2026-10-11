"""Single controlled status-panel interpreter, independent of fixture state."""


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
