// SPDX-License-Identifier: GPL-2.0-only
// Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#include <cstdlib>
#include <iostream>
#include <sstream>

using namespace std;

int main(int argc, char **argv)
{
    int i;
    stringstream cmd;

    cmd << "python -m remote_sync.remote_bisync";

    for(i = 1; i < argc; i++)
        cmd << " " << argv[i];

    system(cmd.str().c_str());

    return 0;
}
