#pragma once

#include <cstddef>

namespace algo {

template <typename T>
T max_value(T a, T b) { return a > b ? a : b; }

template <typename T>
class Box {
public:
    T get() const;
    void set(T value);

private:
    T value_{};
};

template <>
class Box<bool> {
public:
    bool get() const;
};

template class Box<double>;

}  // namespace algo
