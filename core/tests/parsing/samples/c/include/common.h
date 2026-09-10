#ifndef COMMON_H
#define COMMON_H

#define SCALE_FACTOR 3
#define SCALE(x) ((x) * SCALE_FACTOR)
#define MAX(a, b) ((a) > (b) ? (a) : (b))

typedef struct CommonConfig {
    int scale;
} CommonConfig;

int common_scale(int value);

#endif
