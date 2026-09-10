#ifndef TYPES_H
#define TYPES_H

typedef struct Point {
    int x;
    int y;
} Point;

typedef struct {
    int width;
    int height;
} Rect;

struct Node {
    int value;
    struct Node *next;
};

union Value {
    int as_int;
    float as_float;
};

enum Color { COLOR_RED, COLOR_GREEN };

typedef int length_t;

typedef void (*callback_t)(int event);

#endif
