"""OpenGL numbers and shader texts of the 3D view (only what the view needs; OpenGL 2.1 / ES 2.0 style, so old graphics work)."""

GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x100
GL_DEPTH_TEST = 0xB71
GL_BLEND = 0xBE2
GL_LINES = 0x1
GL_TRIANGLES = 0x4
GL_FLOAT = 0x1406
GL_SRC_ALPHA = 0x302
GL_ONE_MINUS_SRC_ALPHA = 0x303
GL_FALSE = 0
GL_TRUE = 1

FLOATS_PER_VERTEX = 9  # position, normal, colour
BYTES_PER_FLOAT = 4
MULTISAMPLES = 4
DEPTH_BITS = 24
MIN_GL_MAJOR = 2  # OpenGL 2.0 or ES 2.0 (shaders)

VERTEX_SHADER = """
uniform mat4 u_mvp;
uniform mat4 u_normal;
attribute vec3 a_position;
attribute vec3 a_normal;
attribute vec3 a_color;
varying vec3 v_normal;
varying vec3 v_color;
void main() {
    gl_Position = u_mvp * vec4(a_position, 1.0);
    v_normal = (u_normal * vec4(a_normal, 0.0)).xyz;
    v_color = a_color;
}
"""

# Two-sided light: the sign of a normal on a revolved piece is not tracked (as in the SVG view before).
FRAGMENT_SHADER = """
uniform vec3 u_light;
uniform vec3 u_params;  // ambient light, 1 = lit and 0 = flat colour, opacity (a float uniform has no safe setter in PySide6)
varying vec3 v_normal;
varying vec3 v_color;
void main() {
    float length_ = length(v_normal);
    float lit = length_ > 0.0 ? abs(dot(v_normal / length_, u_light)) : 0.0;
    float shade = mix(1.0, u_params.x + (1.0 - u_params.x) * lit, u_params.y);
    gl_FragColor = vec4(v_color * shade, u_params.z);
}
"""
DESKTOP_HEADER = "#version 120\n"
ES_HEADER = "precision mediump float;\n"
