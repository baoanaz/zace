#pragma once

#include "base.hpp"

namespace app {

class Service : public Base {
public:
    Service();
    void run() override;
    int score() const override;

private:
    int value_;
};

class Helper;
class Extended : public Service, protected Base {
public:
    void run() override;
};

}  // namespace app
