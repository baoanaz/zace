#ifndef MACROS_H
#define MACROS_H

#define MAX_LEN 128
#define SQUARE(x) ((x) * (x))
#define CONCAT(a, b) a##b
#define LOG(fmt, ...) report(fmt, __VA_ARGS__)

#endif
