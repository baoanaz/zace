#ifndef FNPTR_H
#define FNPTR_H

struct Ops {
    int (*apply)(int, int);
    int (*undo)(int, int);
};

extern const struct Ops default_ops;

#endif
