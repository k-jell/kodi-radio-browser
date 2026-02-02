from __future__ import annotations

import base64
import json
import random
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
from resources.lib.languagecodes import LanguageCode

addon_id: str = "plugin.audio.radiobrowser"
addon: xbmcaddon.Addon = xbmcaddon.Addon(id=addon_id)

base_url: str = sys.argv[0]
addon_handle = int(sys.argv[1])
args = urllib.parse.parse_qs(sys.argv[2][1:])

xbmcplugin.setContent(addon_handle, "songs")

profile: str = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
mystations_path: str = profile + "/mystations.json"

PAGE_LIMIT: int = 500

DEFAULT_ICON = {"icon": "DefaultFolder.png"}


class MyStations:
    def __init__(self, my_stations: dict[str, Any]):
        self.stations = my_stations


MY_STATIONS: MyStations = MyStations({})


def get_radiobrowser_base_urls() -> list[str]:
    """Get all base urls of all currently available radiobrowser servers.

    Returns:
    list: a list of strings

    """
    hosts: list[str] = []
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
    return ["https://" + x for x in hosts]


def language(language_id: int) -> str:
    return addon.getLocalizedString(language_id)


def build_url(query: dict[str, int | str | bytes]) -> str:
    return base_url + "?" + urllib.parse.urlencode(query)


def add_link(stationuuid: str, name: str, url: str, favicon: str, bitrate: str) -> None:
    li = xbmcgui.ListItem(name)
    li.setArt({"icon": favicon, "thumb": favicon, "fanart": favicon})

    li.setProperty("IsPlayable", "true")
    li.setProperty("playlist_type_hint", str(xbmc.PLAYLIST_MUSIC))
    li.setProperty("StationName", name)
    li.setInfo(type="Video", infoLabels={"Size": bitrate, "Album": name})
    local_url = build_url({"mode": "play", "stationuuid": stationuuid})
    li.setProperty("mimetype", "audio")

    if stationuuid in MY_STATIONS.stations:
        context_title = language(LanguageCode.REMOVE_STATION.value)
        context_url = build_url({"mode": "delstation", "stationuuid": stationuuid})
    else:
        context_title = language(LanguageCode.ADD_STATION.value)
        context_url = build_url(
            {
                "mode": "addstation",
                "stationuuid": stationuuid,
                "name": name.encode("utf-8"),
                "url": url,
                "favicon": favicon,
                "bitrate": bitrate,
            },
        )

    xbmc.log(local_url)
    li.addContextMenuItems([(context_title, f"RunPlugin({context_url})")])

    xbmcplugin.addDirectoryItem(handle=addon_handle, url=local_url, listitem=li, isFolder=False)


def download_file(
    uri: str, param: dict[str, Any] | None, url_parameter: dict[str, Any] | None = None
) -> bytes:
    """Download file with the correct headers set.

    Returns:
    a string result

    """
    if url_parameter:
        url_parameter_encoded = urllib.parse.urlencode(url_parameter)
        uri = uri + "?" + url_parameter_encoded
    param_encoded = None
    if param is not None:
        param_encoded = json.dumps(param).encode("utf-8")
        xbmc.log("Request to " + uri + " Params: " + ",".join(param))
    else:
        xbmc.log("Request to " + uri)

    if not uri.startswith("http"):
        xbmc.log("URI needs to be http(s).", xbmc.LOGERROR)
        msg = "Invalid url"
        raise ValueError(msg)
    req = urllib.request.Request(uri, param_encoded)
    req.add_header("User-Agent", "KodiRadioBrowser/2.0.0beta")
    req.add_header("Content-Type", "application/json")
    response = urllib.request.urlopen(req)
    data = response.read()

    response.close()
    return data


def download_api_file(
    path: str,
    param: dict[str, Any] | None,
    url_parameter: dict[str, str | int] | None = None,
) -> bytes:
    """Download file with relative url from a random api server.

    Retry with other api servers if failed.

    Returns:
    a string result

    """
    servers = get_radiobrowser_base_urls()
    for i, server_base in enumerate(servers):
        xbmc.log("Random server: " + server_base + " Try: " + str(i))
        uri = server_base + path

        try:
            return download_file(uri, param, url_parameter=url_parameter)
        except (ValueError, urllib.error.URLError) as e:
            xbmc.log("Unable to download from api url: " + uri, xbmc.LOGERROR)
            xbmc.log(str(e))
    return b""


def add_playable_link(data: bytes) -> None:
    data_decoded = json.loads(data)
    for station in data_decoded:
        add_link(
            station["stationuuid"],
            station["name"],
            station["url"],
            station["favicon"],
            station["bitrate"],
        )


def read_file(filepath: str) -> Any:
    with Path(filepath).open() as read_file:
        return json.load(read_file)


def write_file(filepath: str, data: Any) -> None:
    with Path(filepath).open("w") as write_file:
        return json.dump(data, write_file)


def add_to_my_stations(stationuuid: str, name: str, url: str, favicon: str, bitrate: str) -> None:
    MY_STATIONS.stations[stationuuid] = {
        "stationuuid": stationuuid,
        "name": name,
        "url": url,
        "bitrate": bitrate,
        "favicon": favicon,
    }
    write_file(mystations_path, MY_STATIONS.stations)


def del_from_my_stations(stationuuid: str) -> None:
    if stationuuid in MY_STATIONS.stations:
        del MY_STATIONS.stations[stationuuid]
        write_file(mystations_path, MY_STATIONS.stations)
        xbmc.executebuiltin("Container.Refresh")


def create_directory_item(
    url_args: dict[str, str | bytes | int],
    name: str,
    art_args: dict[str, str],
) -> None:
    local_url = build_url(url_args)
    li = xbmcgui.ListItem(name)
    li.setArt(art_args)
    xbmcplugin.addDirectoryItem(handle=addon_handle, url=local_url, listitem=li, isFolder=True)


def build_menu() -> None:
    create_directory_item(
        {"mode": "stations", "url": "/json/stations/topclick/100"},
        language(LanguageCode.TOP_CLICKED.value),
        DEFAULT_ICON,
    )
    create_directory_item(
        {"mode": "stations", "url": "/json/stations/topvote/100"},
        language(LanguageCode.TOP_VOTED.value),
        DEFAULT_ICON,
    )
    create_directory_item(
        {"mode": "stations", "url": "/json/stations/lastchange/100"},
        language(LanguageCode.LAST_CHANGED.value),
        DEFAULT_ICON,
    )
    create_directory_item(
        {"mode": "stations", "url": "/json/stations/lastclick/100"},
        language(LanguageCode.LAST_CLICKED.value),
        DEFAULT_ICON,
    )
    create_directory_item(
        {"mode": "tags"},
        language(LanguageCode.TAGS.value),
        DEFAULT_ICON,
    )
    create_directory_item(
        {"mode": "countries"},
        language(LanguageCode.COUNTRIES.value),
        DEFAULT_ICON,
    )
    create_directory_item(
        {"mode": "search"},
        language(LanguageCode.SEARCH.value),
        DEFAULT_ICON,
    )
    create_directory_item(
        {"mode": "mystations"},
        language(LanguageCode.MY_STATIONS.value),
        DEFAULT_ICON,
    )
    xbmcplugin.endOfDirectory(addon_handle)


def build_tags_list(args: dict[str, Any]) -> None:
    page = args.get("page")
    if page is not None:
        try:
            page = int(page[0])
        except (KeyError, TypeError, IndexError):
            page = 0
    else:
        page = 0

    url_parameter: dict[str, str | int] = {
        "limit": PAGE_LIMIT,
        "offset": page * PAGE_LIMIT,
    }

    data = download_api_file("/json/tags", None, url_parameter=url_parameter)
    data_decoded = json.loads(data)
    tag_name = ""

    for tag in data_decoded:
        tag_name = tag.get("name", "")
        if int(tag["stationcount"]) > 1:
            try:
                create_directory_item(
                    {
                        "mode": "stations",
                        "key": "tag",
                        "value": base64.b32encode(tag_name.encode("utf-8")),
                    },
                    tag_name,
                    DEFAULT_ICON,
                )
            except Exception as e:
                xbmcgui.Dialog().notification("Error", repr(e))

    create_directory_item(
        {
            "mode": "tags",
            "page": page + 1,
            "value": base64.b32encode(tag_name.encode("utf-8")),
        },
        "Next ->",
        DEFAULT_ICON,
    )
    xbmcplugin.endOfDirectory(addon_handle)


def build_countries_list() -> None:
    data = download_api_file("/json/countries", None)
    data_decoded = json.loads(data)
    for tag in data_decoded:
        country_name = tag["name"]
        if not country_name:
            continue
        if int(tag["stationcount"]) > 1:
            try:
                create_directory_item(
                    {
                        "mode": "states",
                        "country": base64.b32encode(country_name.encode("utf-8")),
                    },
                    country_name,
                    DEFAULT_ICON,
                )
            except Exception as e:
                xbmc.log("Station count is not of type int", xbmc.LOGERROR)
                xbmc.log(str(e))

    xbmcplugin.endOfDirectory(addon_handle)


def build_states_list(args: dict[str, Any]) -> None:
    country = args["country"][0]
    country = base64.b32decode(country)
    country = country.decode("utf-8")

    data = download_api_file("/json/states/" + urllib.parse.quote(country) + "/", None)
    data_decoded = json.loads(data)

    create_directory_item(
        {
            "mode": "stations",
            "key": "country",
            "value": base64.b32encode(country.encode("utf-8")),
        },
        language(LanguageCode.ALL.value),
        DEFAULT_ICON,
    )

    for tag in data_decoded:
        state_name = tag["name"]
        if int(tag["stationcount"]) > 1:
            try:
                create_directory_item(
                    {
                        "mode": "stations",
                        "key": "state",
                        "value": base64.b32encode(state_name.encode("utf-8")),
                    },
                    state_name,
                    DEFAULT_ICON,
                )
            except Exception as e:
                xbmc.log("Stationcount is not of type int", xbmc.LOGERROR)
                xbmc.log(str(e))

    xbmcplugin.endOfDirectory(addon_handle)


def build_stations_search(args: dict[str, Any]) -> None:
    url = "/json/stations/search"
    param: dict[str, Any] = {}
    if "url" in args:
        url = args["url"][0]
    else:
        key = args["key"][0]
        value = base64.b32decode(args["value"][0])
        value = value.decode("utf-8")
        param = {key: value}
        param["order"] = "clickcount"
        param["reverse"] = True

    data = download_api_file(url, param)
    add_playable_link(data)
    xbmcplugin.endOfDirectory(addon_handle)


def play_station(args: dict[str, Any]) -> None:
    stationuuid = urlencode({"uuids": args["stationuuid"][0]})
    data = download_api_file("/json/stations/byuuid?" + stationuuid, None)
    data_decoded = json.loads(data)
    data_decoded = data_decoded[0]
    uri = data_decoded["url"]
    li = xbmcgui.ListItem(path=uri)
    li.setProperty("IsPlayable", "true")
    li.setProperty("playlist_type_hint", str(xbmc.PLAYLIST_MUSIC))
    li.setProperty("StationName", data_decoded["name"])
    favicon = data_decoded.get("favicon", "")
    li.setArt({"icon": favicon, "thumb": favicon, "fanart": favicon})
    li.setInfo(
        type="Video",
        infoLabels={"size": data_decoded["bitrate"], "Album": data_decoded.get("name", "")},
    )
    xbmcplugin.setResolvedUrl(addon_handle, succeeded=True, listitem=li)


def search_stations() -> None:
    dialog = xbmcgui.Dialog()
    d = dialog.input(language(32011), type=xbmcgui.INPUT_ALPHANUM)

    escaped = urllib.parse.quote(d)

    url = "/json/stations/byname/" + escaped
    data = download_api_file(url, None)
    add_playable_link(data)

    xbmcplugin.endOfDirectory(addon_handle)


def build_my_stations() -> None:
    for station in list(MY_STATIONS.stations.values()):
        add_link(
            station["stationuuid"],
            station["name"],
            station["url"],
            station["favicon"],
            station["bitrate"],
        )
    add_station_url = build_url({"mode": "addcustom"})
    li = xbmcgui.ListItem("Add Station")
    xbmcplugin.addDirectoryItem(
        handle=addon_handle,
        url=add_station_url,
        listitem=li,
        isFolder=False,
    )
    xbmcplugin.endOfDirectory(addon_handle)


def add_station(args: dict[str, Any]) -> None:
    favicon = args["favicon"][0] if "favicon" in args else ""
    add_to_my_stations(
        args["stationuuid"][0],
        args["name"][0],
        args["url"][0],
        favicon,
        args["bitrate"][0],
    )


def delete_station(args: dict[str, Any]) -> None:
    del_from_my_stations(args["stationuuid"][0])


def add_custom_station() -> None:
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
    add_to_my_stations("dd98c499-a0c4-4019-a35e-99caa6940407", title, url, "", "192")
    refresh_url = build_url({"mode": "mystations"})
    xbmc.executebuiltin("Container.Refresh(" + refresh_url + ")")


def router(mode: str | None, args: dict[str, Any]) -> None:
    if mode is None:
        build_menu()
    elif mode == "tags":
        build_tags_list(args)
    elif mode == "countries":
        build_countries_list()
    elif mode == "states":
        build_states_list(args)
    elif mode == "stations":
        build_stations_search(args)
    elif mode == "play":
        play_station(args)
    elif mode == "search":
        search_stations()
    elif mode == "mystations":
        build_my_stations()
    elif mode == "addstation":
        add_station(args)
    elif mode == "delstation":
        delete_station(args)
    elif mode == "addcustom":
        add_custom_station()


def main() -> None:
    # create storage
    if not xbmcvfs.exists(profile):
        xbmcvfs.mkdir(profile)

    if xbmcvfs.exists(mystations_path):
        MY_STATIONS.stations = read_file(mystations_path)
    else:
        write_file(mystations_path, MY_STATIONS.stations)

    mode = args.get("mode", None)
    if mode is not None:
        mode = mode[0]
    router(mode, args)


if __name__ == "__main__":
    main()
