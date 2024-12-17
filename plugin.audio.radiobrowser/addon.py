import base64
import json
import random
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
from resources.lib.languagecodes import LanguageCode

addonID: str = "plugin.audio.radiobrowser"
addon: xbmcaddon.Addon = xbmcaddon.Addon(id=addonID)

base_url: str = sys.argv[0]
addon_handle = int(sys.argv[1])
args: Dict[str, Any] = urllib.parse.parse_qs(sys.argv[2][1:])

xbmcplugin.setContent(addon_handle, "songs")

profile: str = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
mystations_path: str = profile + "/mystations.json"

PAGE_LIMIT: int = 500

DEFAULT_ICON: Dict[str, str] = {"icon": "DefaultFolder.png"}


class MyStations:
    def __init__(self, my_stations: Dict[str, Any]):
        self.stations = my_stations


MY_STATIONS: MyStations = MyStations({})


def get_radiobrowser_base_urls() -> List[str]:
    """
    Get all base urls of all currently available radiobrowser servers

    Returns:
    list: a list of strings

    """
    hosts: List[str] = []
    # get all hosts from DNS
    ips = socket.getaddrinfo("all.api.radio-browser.info", 80, 0, 0, socket.IPPROTO_TCP)
    for ip_tuple in ips:
        ip = ip_tuple[4][0]

        # do a reverse lookup on every one of the ips to have a nice name for it
        host_addr = socket.gethostbyaddr(ip)

        # add the name to a list if not already in there
        if host_addr[0] not in hosts:
            hosts.append(host_addr[0])

    # sort list of names
    random.shuffle(hosts)
    # add "https://" in front to make it an url
    xbmc.log("Found hosts: " + ",".join(hosts))
    return list(["https://" + x for x in hosts])


def LANGUAGE(id: int) -> str:
    # return id
    # return "undefined"
    return addon.getLocalizedString(id)


def build_url(query: Dict[str, "int | str | bytes"]):
    return base_url + "?" + urllib.parse.urlencode(query)


def addLink(stationuuid: str, name: str, url: str, favicon: str, bitrate: str):
    li = xbmcgui.ListItem(name)
    li.setArt({"icon": favicon})
    li.setProperty("IsPlayable", "true")
    li.setInfo(type="Video", infoLabels={"Album": name, "Size": bitrate})
    localUrl = build_url({"mode": "play", "stationuuid": stationuuid})

    if stationuuid in MY_STATIONS.stations:
        contextTitle = LANGUAGE(LanguageCode.REMOVE_STATION.value)
        contextUrl = build_url({"mode": "delstation", "stationuuid": stationuuid})
    else:
        contextTitle = LANGUAGE(LanguageCode.ADD_STATION.value)
        contextUrl = build_url(
            {
                "mode": "addstation",
                "stationuuid": stationuuid,
                "name": name.encode("utf-8"),
                "url": url,
                "favicon": favicon,
                "bitrate": bitrate,
            }
        )

    li.addContextMenuItems([(contextTitle, "RunPlugin(%s)" % (contextUrl))])

    xbmcplugin.addDirectoryItem(
        handle=addon_handle, url=localUrl, listitem=li, isFolder=False
    )


def downloadFile(uri: str, param, url_parameter: Dict[str, Any] = {}) -> bytes:
    """
    Download file with the correct headers set

    Returns:
    a string result

    """
    if url_parameter:
        url_parameter_encoded = urllib.parse.urlencode(url_parameter)
        uri = uri + "?" + url_parameter_encoded
    paramEncoded = None
    if param is not None:
        paramEncoded = json.dumps(param).encode("utf-8")
        xbmc.log("Request to " + uri + " Params: " + ",".join(param))
    else:
        xbmc.log("Request to " + uri)

    req = urllib.request.Request(uri, paramEncoded)
    req.add_header("User-Agent", "KodiRadioBrowser/2.0.0beta")
    req.add_header("Content-Type", "application/json")
    response = urllib.request.urlopen(req)
    data = response.read()

    response.close()
    return data


def downloadApiFile(
    path: str,
    param: "Dict[str, Any] | None",
    url_parameter: Dict[str, "str | int"] = {},
) -> bytes:
    """
    Download file with relative url from a random api server.
    Retry with other api servers if failed.

    Returns:
    a string result

    """
    servers = get_radiobrowser_base_urls()
    i = 0
    for server_base in servers:
        xbmc.log("Random server: " + server_base + " Try: " + str(i))
        uri = server_base + path

        try:
            data = downloadFile(uri, param, url_parameter=url_parameter)
            return data
        except Exception as e:
            xbmc.log("Unable to download from api url: " + uri, xbmc.LOGERROR)
            xbmc.log(str(e))
            pass
        i += 1
    return b""


def addPlayableLink(data: bytes):
    dataDecoded = json.loads(data)
    for station in dataDecoded:
        addLink(
            station["stationuuid"],
            station["name"],
            station["url"],
            station["favicon"],
            station["bitrate"],
        )


def readFile(filepath: str) -> Any:
    with open(filepath, "r") as read_file:
        return json.load(read_file)


def writeFile(filepath: str, data: Any):
    with open(filepath, "w") as write_file:
        return json.dump(data, write_file)


def addToMyStations(stationuuid: str, name: str, url: str, favicon: str, bitrate: str):
    MY_STATIONS.stations[stationuuid] = {
        "stationuuid": stationuuid,
        "name": name,
        "url": url,
        "bitrate": bitrate,
        "favicon": favicon,
    }
    writeFile(mystations_path, MY_STATIONS.stations)


def delFromMyStations(stationuuid: str):
    if stationuuid in MY_STATIONS.stations:
        del MY_STATIONS.stations[stationuuid]
        writeFile(mystations_path, MY_STATIONS.stations)
        xbmc.executebuiltin("Container.Refresh")


def createDirectoryItem(
    urlArgs: Dict[str, "str | bytes | int"], name: str, artArgs: Dict[str, str]
):
    localUrl = build_url(urlArgs)
    li = xbmcgui.ListItem(name)
    li.setArt(artArgs)
    xbmcplugin.addDirectoryItem(
        handle=addon_handle, url=localUrl, listitem=li, isFolder=True
    )


def buildMenu() -> None:
    createDirectoryItem(
        {"mode": "stations", "url": "/json/stations/topclick/100"},
        LANGUAGE(LanguageCode.TOP_CLICKED.value),
        DEFAULT_ICON,
    )
    createDirectoryItem(
        {"mode": "stations", "url": "/json/stations/topvote/100"},
        LANGUAGE(LanguageCode.TOP_VOTED.value),
        DEFAULT_ICON,
    )
    createDirectoryItem(
        {"mode": "stations", "url": "/json/stations/lastchange/100"},
        LANGUAGE(LanguageCode.LAST_CHANGED.value),
        DEFAULT_ICON,
    )
    createDirectoryItem(
        {"mode": "stations", "url": "/json/stations/lastclick/100"},
        LANGUAGE(LanguageCode.LAST_CLICKED.value),
        DEFAULT_ICON,
    )
    createDirectoryItem(
        {"mode": "tags"},
        LANGUAGE(LanguageCode.TAGS.value),
        DEFAULT_ICON,
    )
    createDirectoryItem(
        {"mode": "countries"},
        LANGUAGE(LanguageCode.COUNTRIES.value),
        DEFAULT_ICON,
    )
    createDirectoryItem(
        {"mode": "search"},
        LANGUAGE(LanguageCode.SEARCH.value),
        DEFAULT_ICON,
    )
    createDirectoryItem(
        {"mode": "mystations"},
        LANGUAGE(LanguageCode.MY_STATIONS.value),
        DEFAULT_ICON,
    )
    xbmcplugin.endOfDirectory(addon_handle)


def buildTagsList(args: Dict[str, Any]) -> None:
    page = args.get("page")
    if page is not None:
        try:
            page = int(page[0])
        except (KeyError, TypeError, IndexError):
            page = 0
    else:
        page = 0

    url_parameter: Dict[str, "str | int"] = {
        "limit": PAGE_LIMIT,
        "offset": page * PAGE_LIMIT,
    }

    data = downloadApiFile("/json/tags", None, url_parameter=url_parameter)
    dataDecoded = json.loads(data)
    tagName = ""

    for tag in dataDecoded:
        tagName = tag.get("name", "")
        if int(tag["stationcount"]) > 1:
            try:
                createDirectoryItem(
                    {
                        "mode": "stations",
                        "key": "tag",
                        "value": base64.b32encode(tagName.encode("utf-8")),
                    },
                    tagName,
                    DEFAULT_ICON,
                )
            except Exception as e:
                xbmcgui.Dialog().notification("Error", repr(e))
                pass

    createDirectoryItem(
        {
            "mode": "tags",
            "page": page + 1,
            "value": base64.b32encode(tagName.encode("utf-8")),
        },
        "Next ->",
        DEFAULT_ICON,
    )
    xbmcplugin.endOfDirectory(addon_handle)


def buildCountriesList() -> None:
    data = downloadApiFile("/json/countries", None)
    dataDecoded = json.loads(data)
    for tag in dataDecoded:
        countryName = tag["name"]
        if not countryName:
            continue
        if int(tag["stationcount"]) > 1:
            try:
                createDirectoryItem(
                    {
                        "mode": "states",
                        "country": base64.b32encode(countryName.encode("utf-8")),
                    },
                    countryName,
                    DEFAULT_ICON,
                )
            except Exception as e:
                xbmc.log("Stationcount is not of type int", xbmc.LOGERROR)
                xbmc.log(str(e))
                pass

    xbmcplugin.endOfDirectory(addon_handle)


def buildStatesList(args: Dict[str, Any]) -> None:
    country = args["country"][0]
    country = base64.b32decode(country)
    country = country.decode("utf-8")

    data = downloadApiFile("/json/states/" + urllib.parse.quote(country) + "/", None)
    dataDecoded = json.loads(data)

    createDirectoryItem(
        {
            "mode": "stations",
            "key": "country",
            "value": base64.b32encode(country.encode("utf-8")),
        },
        LANGUAGE(LanguageCode.ALL.value),
        DEFAULT_ICON,
    )

    for tag in dataDecoded:
        stateName = tag["name"]
        if int(tag["stationcount"]) > 1:
            try:
                createDirectoryItem(
                    {
                        "mode": "stations",
                        "key": "state",
                        "value": base64.b32encode(stateName.encode("utf-8")),
                    },
                    stateName,
                    DEFAULT_ICON,
                )
            except Exception as e:
                xbmc.log("Stationcount is not of type int", xbmc.LOGERROR)
                xbmc.log(str(e))
                pass

    xbmcplugin.endOfDirectory(addon_handle)


def buildStationsSearch(args: Dict[str, Any]) -> None:
    url = "/json/stations/search"
    param: Dict[str, Any] = {}
    if "url" in args:
        url = args["url"][0]
    else:
        key = args["key"][0]
        value = base64.b32decode(args["value"][0])
        value = value.decode("utf-8")
        param = dict({key: value})
        param["order"] = "clickcount"
        param["reverse"] = True

    data = downloadApiFile(url, param)
    addPlayableLink(data)
    xbmcplugin.endOfDirectory(addon_handle)


def playStation(args: Dict[str, Any]) -> None:
    stationuuid = args["stationuuid"][0]
    data = downloadApiFile("/json/url/" + str(stationuuid), None)
    dataDecoded = json.loads(data)
    uri = dataDecoded["url"]
    xbmcplugin.setResolvedUrl(addon_handle, True, xbmcgui.ListItem(path=uri))


def searchStations() -> None:
    dialog = xbmcgui.Dialog()
    d = dialog.input(LANGUAGE(32011), type=xbmcgui.INPUT_ALPHANUM)

    url = "/json/stations/byname/" + d
    data = downloadApiFile(url, None)
    addPlayableLink(data)

    xbmcplugin.endOfDirectory(addon_handle)


def buildMyStations() -> None:
    for station in list(MY_STATIONS.stations.values()):
        addLink(
            station["stationuuid"],
            station["name"],
            station["url"],
            station["favicon"],
            station["bitrate"],
        )
    addStationURL = build_url({"mode": "addcustom"})
    li = xbmcgui.ListItem("Add Station")
    xbmcplugin.addDirectoryItem(
        handle=addon_handle, url=addStationURL, listitem=li, isFolder=False
    )
    xbmcplugin.endOfDirectory(addon_handle)


def addStation(args: Dict[str, Any]) -> None:
    favicon = args["favicon"][0] if "favicon" in args else ""
    addToMyStations(
        args["stationuuid"][0],
        args["name"][0],
        args["url"][0],
        favicon,
        args["bitrate"][0],
    )


def deleteStation(args: Dict[str, Any]) -> None:
    delFromMyStations(args["stationuuid"][0])


def addCustomStation() -> None:
    kb = xbmc.Keyboard("default", "heading")
    kb.setDefault("title")  # optional
    kb.setHeading("Enter Title")  # optional
    kb.doModal()
    title = ""
    if kb.isConfirmed():
        title = kb.getText()
    kb = xbmc.Keyboard("default", "heading")
    kb.setDefault("URL")  # optional
    kb.setHeading("Enter URL")  # optional
    kb.doModal()
    url = ""
    if kb.isConfirmed():
        url = kb.getText()
    addToMyStations("dd98c499-a0c4-4019-a35e-99caa6940407", title, url, "", "192")
    refresh_url = build_url({"mode": "mystations"})
    xbmc.executebuiltin("Container.Refresh(" + refresh_url + ")")


def router(mode: "str | None", args: Dict[str, Any]) -> None:
    if mode is None:
        buildMenu()
    elif mode == "tags":
        buildTagsList(args)
    elif mode == "countries":
        buildCountriesList()
    elif mode == "states":
        buildStatesList(args)
    elif mode == "stations":
        buildStationsSearch(args)
    elif mode == "play":
        playStation(args)
    elif mode == "search":
        searchStations()
    elif mode == "mystations":
        buildMyStations()
    elif mode == "addstation":
        addStation(args)
    elif mode == "delstation":
        deleteStation(args)
    elif mode == "addcustom":
        addCustomStation()


def main():
    # create storage
    if not xbmcvfs.exists(profile):
        xbmcvfs.mkdir(profile)

    if xbmcvfs.exists(mystations_path):
        MY_STATIONS.stations = readFile(mystations_path)
    else:
        writeFile(mystations_path, MY_STATIONS.stations)

    mode = args.get("mode", None)
    if mode is not None:
        mode = mode[0]
    router(mode, args)


if __name__ == "__main__":
    main()
