from core.ice import ice_study
from model.user import User
from model.courses import Courses
from model.course import Course
from plug.Plug import Plug


def main():
    ice = ice_study(main)
    ice = Plug(ice)
    user = User(ice)
    courses = Courses(user)
    Course(courses)
    return ice


if __name__ == "__main__":
    main()