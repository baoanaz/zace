#include <cstddef>

namespace app {

#define DECLARE_ACCESSOR(name) \
    int name() const { return name##_; }

class Widget {
public:
    DECLARE_ACCESSOR(width)
    int total() const { return width() + height(); }

private:
    int width_{};
    int height_{};
};

template <typename T>
class Registry {
public:
    T *find(const char *key);

private:
    DECLARE_ACCESSOR(size)
};

}  // namespace app
