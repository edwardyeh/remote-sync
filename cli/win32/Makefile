####### Environment Define #####################################################
CPP_SRC_DIR = .

CC       = g++
RM       = rm 
MKDIR    = mkdir
ENV      = LINUX
CFLAGS   = -D$(ENV) -m64
CXXFLAGS = $(CFLAGS)
LDFLAGS  = -lm
################################################################################

ifeq ($(MAKECMDGOALS), debug)
    CFLAGS   += -g3 -w
    CXXFLAGS += -g3 -w
else
    CFLAGS   += -O3 -w
    CXXFLAGS += -O3 -w
endif

vpath %.cpp $(CPP_SRC_DIR)

CPP_SRCS = $(foreach var, $(CPP_SRC_DIR), $(wildcard $(addsuffix /*.cpp, $(var))))
CPP_EXE  = $(notdir $(CPP_SRCS:.cpp=.exe))

.PHONY: all debug clean 

all debug: $(CPP_EXE)

%.exe: %.cpp
	$(CC) -o $@ $^ $(LDFLAGS) 
clean:
	-$(RM) -rf *.exe

