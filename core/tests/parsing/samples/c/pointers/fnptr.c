#include "fnptr.h"

static int add(int a, int b) { return a + b; }
static int sub(int a, int b) { return a - b; }
static int mul(int a, int b) { return a * b; }

typedef int (*binop)(int, int);

static int (*current)(int, int) = add;

static int (*const op_table[2])(int, int) = {add, sub};

static const struct Ops default_ops = {.apply = mul, .undo = sub};

int apply_binop(int a, int b) {
    binop local = sub;
    local(a, b);
    current(a, b);
    default_ops.apply(a, b);
    return op_table[0](a, b) + (current = mul, current(a, b));
}
